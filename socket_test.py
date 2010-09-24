#!/usr/bin/python

"""Playing with sockets.  I need to spin up a one-shot web server."""

import cgi
import socket
import BaseHTTPServer

class MyHandler(BaseHTTPServer.BaseHTTPRequestHandler):
  def log_message(self, format, *args):
    """Don't log anything."""
    pass

  def do_GET(self):
    params = cgi.parse_qs(self.path.split('?')[1])
    self.server.result = params
    msg = '<h1>All Done</h1>\n<p>Thanks!  You may close this window now.</p>\n'
    self.send_response(200)
    self.send_header('Content-Length', str(len(msg)))
    self.end_headers()
    print >>self.wfile, msg

class MyServer(BaseHTTPServer.HTTPServer):
  def __init__(self, handler_class=MyHandler):
    self.port = self.get_random_port()
    server_address = ('', self.port)
    # Darned old-style classes.
    BaseHTTPServer.HTTPServer.__init__(self, server_address, handler_class)
    # For returning a result.
    self.result = None

  def get_random_port(self):
    # Make an anonymous socket on a random port.  Once closed, that port is
    # free for us to use for a while.
    sock = socket.socket()
    sock.bind(('', 0))
    port = sock.getsockname()[1]
    sock.close()
    return port

  def my_url(self):
    return 'http://%s:%d' % (socket.getfqdn(), self.port)

  def serve_until_result(self):
    while not self.result:
      self.handle_request()


def main():
  httpd = MyServer()
  print httpd.my_url()
  httpd.serve_until_result()
  
  print 'result: [%s]' % str(httpd.result)

if __name__ == '__main__':
  main()