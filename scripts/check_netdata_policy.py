"""Exercise the real nginx access policy against a harmless fake upstream."""
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time


def validate_policy(source):
    seen = []
    class Fake(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.path)
            self.send_response(200)
            self.send_header('Content-Length','2')
            self.end_headers()
            self.wfile.write(b'ok')
        def log_message(self, *_args):
            pass
    upstream = ThreadingHTTPServer(('127.0.0.1',0),Fake)
    upstream.daemon_threads = True
    thread = threading.Thread(target=upstream.serve_forever,daemon=True)
    thread.start()
    process = None
    try:
        config = Path(source).read_text()
        registry = config[config.index('map $args $netdata_registry_blocked {'):].split('\n}',1)[0]+'\n}'
        policy = config[config.index('map $uri $netdata_public_blocked {'):].split('\n}',1)[0]+'\n}'
        block = config[config.index('    location ~ ^/netdata/(?<ndpath>.*)$ {'):].split('\n    }',1)[0]+'\n    }'
        block = block.replace('127.0.0.1:19999','127.0.0.1:'+str(upstream.server_port))
        with socket.socket() as reserve:
            reserve.bind(('127.0.0.1',0))
            port = reserve.getsockname()[1]
        with tempfile.TemporaryDirectory(prefix='netdata-policy-') as directory:
            directory = Path(directory)
            full = ('worker_processes 1;\npid '+str(directory/'nginx.pid')+';\nerror_log '+str(directory/'error.log')+' warn;\n'
                    'events { worker_connections 64; }\nhttp {\naccess_log off;\n'
                    'limit_req_zone $binary_remote_addr zone=netdata_cloud_per_ip:1m rate=300r/m;\n'
                    'limit_conn_zone $binary_remote_addr zone=arena_conn_per_ip:1m;\n'+registry+'\n'+policy+'\n'
                    'server { listen 127.0.0.1:'+str(port)+';\n'+block+'\n}\n}\n')
            (directory/'nginx.conf').write_text(full)
            subprocess.run(['nginx','-t','-c',str(directory/'nginx.conf'),'-p',str(directory)],check=True,capture_output=True)
            process = subprocess.Popen(['nginx','-c',str(directory/'nginx.conf'),'-p',str(directory),'-g','daemon off;'],
                                       stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            def query(path, method='GET', headers=None):
                connection = http.client.HTTPConnection('127.0.0.1',port,timeout=3)
                connection.request(method,path,headers=headers or {})
                response = connection.getresponse()
                status = response.status
                response.read()
                connection.close()
                return status
            for attempt in range(30):
                try:
                    if query('/netdata/api/v1/info') == 200:
                        break
                except OSError:
                    time.sleep(.1)
            else:
                raise RuntimeError('policy_nginx_not_ready')
            allowed = ['/netdata/', '/netdata/api/v1/data', '/netdata/v3/index.html',
                       '/netdata/host/local/api/v1/info', '/netdata/node/local/v3/api/v3/settings',
                       '/netdata/api/v3/functions', '/netdata/api/v1/registry?action=hello']
            blocked = ['/netdata/netdata.conf', '/netdata/v3/netdata.conf', '/netdata/debug', '/netdata/exit',
                       '/netdata/mcp', '/netdata/sse', '/netdata/v3/mcp',
                       '/netdata/host/local/sse', '/netdata/node/local/v2/mcp',
                       '/netdata/netdata.conf%3Fx', '/netdata/v3/netdata.conf%3Fx',
                       '/netdata/api/v1/registry?action=access', '/netdata/api/v1/registry?action=hello&action=delete',
                       '/netdata/api/v1/registry?action=%68ello',
                       '/netdata/v3/host/local/exit', '/netdata/mirror', '/netdata/api/v1/manage/health',
                       '/netdata/host/localhost/api/v1/manage/health', '/netdata/v2/api/v3/config',
                       '/netdata/node/local/api/v3/function', '/netdata/api/v1/registry', '/netdata/api/v3/claim',
                       '/netdata/api/v3/bearer_get_token', '/netdata/api/v3/rtc_offer', '/netdata/api/v3/new_control',
                       '/netdata/%61pi/v1/manage/health', '/netdata/%2561pi/v1/manage/health',
                       '/netdata/v3/../api/v1/manage/health']
            for path in allowed:
                if query(path) != 200:
                    raise RuntimeError('policy_read_failed')
            for path in blocked:
                before = len(seen)
                if query(path) != 404 or len(seen) != before:
                    raise RuntimeError('policy_control_leaked')
            for method in ['POST','PUT','DELETE','OPTIONS']:
                before = len(seen)
                status = query('/netdata/api/v3/settings',method)
                if status not in (403, 405) or len(seen) != before:
                    raise RuntimeError(f'policy_write_failed:{method}:status={status}:forwarded={len(seen) != before}')
            for path in ['/netdata/', '/netdata/api/v3/info']:
                before = len(seen)
                status = query(path, headers={'Upgrade':'websocket', 'Connection':'Upgrade',
                                             'Sec-WebSocket-Protocol':'mcp', 'Sec-WebSocket-Version':'13'})
                if status != 404 or len(seen) != before:
                    raise RuntimeError('policy_websocket_forwarded')
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        upstream.shutdown()
        upstream.server_close()
        thread.join(timeout=3)


if __name__ == '__main__':
    validate_policy(Path(__file__).resolve().parents[1] / 'nginx/investment-debate-arena.conf')
    print('netdata_public_policy=passed')
