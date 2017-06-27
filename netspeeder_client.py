import time
from enum import Enum, unique
import struct
import gevent
from gevent.server import StreamServer
from gevent.socket import create_connection
import sys
import socket

@unique
class SocksServerState(Enum):
    First = 0
    Second = 1
    Third = 2
    Final = 3

forwarder_address = ('127.0.0.1', 151)
proxyer_address = ('0.0.0.0', 60000)
proxy_clients = dict()
global forward_socket

def log_print(str):
    print("[%s] %s" % (time.strftime("%H:%M:%S", time.localtime()), str))

class ProxyServer:
    def __init__(self, address):
        StreamServer(address, self.handle).serve_forever()

    def handle(self, socket_fd, address):
        socks5_state = SocksServerState.First
        proxy_clients[socket_fd.fileno()] = socket_fd
        while True:
            try:
                packet = socket_fd.recv(65535)
            except socket.timeout as e:
                gevent.sleep(0)
                continue
            except:
                print(sys.exc_info())
                break
            if len(packet) == 0:
                gevent.sleep(0)
                continue
            log_print("entry")
            if socks5_state == SocksServerState.First:
                socks5_state = self.doFirstState(socket_fd, packet)
            elif socks5_state == SocksServerState.Second:
                socks5_state = self.doSecondState(socket_fd, packet)
            elif socks5_state == SocksServerState.Third:
                self.doThirdState(socket_fd, packet)
            else:
                log_print("break in else")
                break
            if socks5_state == SocksServerState.Final:
                log_print("break Final")
                break
            gevent.sleep(0)
        try:
            del proxy_clients[socket_fd.fileno()]
        except:
            log_print("no key")

    def doFirstState(self, socket_fd, packet):
        ret = SocksServerState.First
        try:
            ver, nmethod, methods = struct.unpack("3B", packet[:3])
        except:
            print(packet)
            return ret
        if ver == 5 and nmethod == 1 and methods == 0:
            content = struct.pack("2B", ver, methods)
            socket_fd.sendall(content)
            ret = SocksServerState.Second
        return ret

    def doSecondState(self, socket_fd, packet):
        fileno = int(socket_fd.fileno())
        state = 1
        header = struct.pack("!IBH", fileno, state, len(packet) - 3)
        content = packet[3:]
        log_print("state 1 send to forward")
        global  forward_socket
        try:
            forward_socket.sendall(header + content)
        except:
            forward_socket = create_connection(forwarder_address)
            return SocksServerState.Final

        (ver, rep, rsv, atyp, ipaddr, ipport) = (5, 0, 0, 1, 0, 0)
        content = struct.pack("!4BIH", ver, rep, rsv, atyp, ipaddr, ipport)
        socket_fd.sendall(content)
        return SocksServerState.Third

    def doThirdState(self, socket_fd, packet):
        fileno = int(socket_fd.fileno())
        state = 2
        header = struct.pack("!IBH", fileno, state, len(packet))
        log_print("state 2 send to forward")
        global forward_socket
        try:
            forward_socket.sendall(header + packet)
        except:
            forward_socket = create_connection(forwarder_address)
            return SocksServerState.Final

def forward_processer():
    last_packet = None
    while True:
        global  forward_socket
        try:
            data = forward_socket.recv(65535)
        except socket.timeout as e:
            gevent.sleep(0)
            continue
        except:
            print(sys.exc_info())
            forward_socket.close()
            try:
                forward_socket = create_connection(forwarder_address)
            except:
                log_print("re connect forward failed")
            gevent.sleep(0)
            continue
        if len(data) == 0:
            gevent.sleep(0)
            continue
        start = 0
        if last_packet != None:
            log_print("reload packet data %d last packet %d" % (len(data), len(last_packet)))
            data = last_packet + data
            last_packet = None
        log_print("recv forward start len %d" % len(data))
        while start < len(data):
            if (start + 6 > len(data)):
                last_packet = data[start:]
                break
            fileno, content_len = struct.unpack("!IH", data[start : start + 6])
            if int(content_len) == 65535:
                client_socket = proxy_clients.get(fileno)
                if client_socket != None:
                    log_print("close %d" % fileno)
                    client_socket.close()
                start = start + 6
                continue
            if (content_len > len(data[start + 6:])):
                last_packet = data[start:]
                log_print("save packet %d  content len %d" % (len(data[start:]), content_len))
                log_print(data[start:])
                break
            log_print("recv forward start %d content %d" % (start, content_len))
            client_socket = proxy_clients.get(fileno)
            if client_socket == None:
                start = start + 6 + content_len
                log_print("no client socket")
                continue
            try:
                client_socket.sendall(data[start + 6 : start + 6 + content_len])
            except:
                log_print("client_socket has closed")
            start = start + 6 + content_len

def proxy_processer():
    ProxyServer(proxyer_address)

def detect_processer():
    while True:
        #print("alive")
        gevent.sleep(5)

if __name__ == '__main__':
    while True:
        try:
            forward_socket = create_connection(forwarder_address)
            break
        except Exception as e:
            log_print("Connect to Forwarder Failed %s" % str(e))
            time.sleep(5)
            continue
    log_print("Connect to Forwarder Success")
    tasks = (gevent.spawn(forward_processer), gevent.spawn(proxy_processer), gevent.spawn(detect_processer))
    gevent.joinall(tasks)
