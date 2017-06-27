from enum import Enum, unique
import struct
import gevent
from gevent.server import StreamServer
from gevent.socket import create_connection, gethostbyname
import time

forwader_address = ('0.0.0.0', 150)

@unique
class ClientState(Enum):
    Second = 1
    Third = 2

clients = dict()
pkt_buff = dict()

def log_print(str, level = 0):
    if level:
        print("[%s] %s" % (time.strftime("%H:%M:%S", time.localtime()), str))

def remote_process(remote_socket, socket_fd, client_fileno):
    while True:
        try:
            packet = remote_socket.recv(1200)
        except:
            log_print("remote socket recv failed", 1)
            if clients.get(client_fileno) != None:
                del clients[client_fileno]
            header = struct.pack("!IH", client_fileno, 65535)
            try:
                socket_fd.sendall(header)
            except:
                log_print("socket_fd send failed 1", 1)
            break
        if len(packet) == 0:
            gevent.sleep(0)
            continue
        header = struct.pack("!IH", client_fileno, len(packet))
        log_print("recv and send remote fileno %d" % client_fileno)
        try:
            socket_fd.sendall(header + packet)
        except:
            log_print("socket_fd send failed 2", 1)
        #gevent.sleep(0)

def process_connect(client_fileno, remote_addr, remote_port, socket_fd):
    ip = gethostbyname(remote_addr)
    port = int(remote_port)
    try:
        log_print("before connect", 1)
        remote_socket = create_connection((ip, port), timeout=5)
        log_print("after  connect", 1)
    except:
        log_print("remote_socket create failed addr %s" % remote_addr, 1)
        if pkt_buff.get(client_fileno) != None:
            del pkt_buff[client_fileno]
        return
    gevent.spawn(remote_process, remote_socket, socket_fd, client_fileno)
    log_print("recv state 1 address %s fileno %d" % (remote_addr, client_fileno))
    clients[client_fileno] = remote_socket
    if pkt_buff.get(client_fileno) != None:
        remote_socket.sendall(pkt_buff.get(client_fileno))
        del pkt_buff[client_fileno]

class ForwardServer:
    def __init__(self, address):
        StreamServer(address, self.handle).serve_forever()

    def handle(self, socket_fd, address):
        last_packet = None
        while True:
            try:
                packet = socket_fd.recv(65535)
            except Exception as e:
                print(str(e))
                break
            if len(packet) == 0:
                gevent.sleep(0)
                continue

            log_print("recv len %d" % len(packet))

            if last_packet != None:
                log_print("reload packet data %d last packet %d" % (len(packet), len(last_packet)))
                packet = last_packet + packet
                last_packet = None
            start = 0
            while start < len(packet):
                client_fileno, client_state, content_len = struct.unpack("!IBH", packet[start : start + 7])
                if (content_len > len(packet[start + 7:])):
                    last_packet = packet[start:]
                    log_print("save packet %d" % len(packet[start:]))
                    break
                start = start + 7

                if int(client_state) == 1:
                    atyp = packet[start]
                    if atyp == 1:
                        remote_addr = struct.unpack("!I", packet[start + 1 : start + 5])[0]
                        remote_port = struct.unpack("!H", packet[start + 5 : start + 7])[0]
                        start = start + 7
                    elif atyp == 3:
                        domain_name_len = int(packet[start + 1])
                        remote_addr = struct.unpack("!%ds" % domain_name_len, packet[start + 2 : start + 2 + domain_name_len])[0]
                        remote_port = struct.unpack("!H", packet[start + 2 + domain_name_len : start + 2 + domain_name_len + 2])[0]
                        start = start + 2 + domain_name_len + 2
                    elif atyp == 4:
                        remote_addr = struct.unpack("!4I", packet[start + 1 : start + 17])[0]
                        remote_port = struct.unpack("!H", packet[start + 17 : start + 19])[0]
                        start = start + 19
                    else:
                        log_print("fatal unknown atyp")
                        break
                    gevent.spawn(process_connect, client_fileno, remote_addr, remote_port, socket_fd)
                elif int(client_state) == 2:
                    log_print("recv state 2")
                    end = start + content_len
                    if clients.get(client_fileno) == None:
                        if pkt_buff.get(client_fileno) == None:
                            pkt_buff[client_fileno] = packet[start:end]
                        else:
                            pkt_buff[client_fileno] = pkt_buff.get(client_fileno) + packet[start:end]
                        start = end
                        log_print("no fileno %d and save pkt" % client_fileno, 1)
                        continue
                    log_print("recv and send state 2 fileno %d" % (client_fileno))
                    remote_socket = clients.get(client_fileno)
                    remote_socket.sendall(packet[start : end])
                    start = end
                else:
                    log_print("fatal unknown client state")
                    break
            gevent.sleep(0)

def is_alive():
    while True:
        log_print("alive", 1)
        gevent.sleep(1)

if __name__ == '__main__':
    gevent.spawn(is_alive)
    ForwardServer(forwader_address)
