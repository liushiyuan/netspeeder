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

def remote_process(remote_socket, socket_fd, client_fileno):
    while True:
        try:
            packet = remote_socket.recv(1200)
        except Exception as e:
            print(str(e))
            clients[client_fileno] = None
            header = struct.pack("!IH", client_fileno, 65535)
            socket_fd.sendall(header)
            break
        if len(packet) == 0:
            gevent.sleep(0)
            continue
        header = struct.pack("!IH", client_fileno, len(packet))
        print("recv and send remote fileno %d" % client_fileno)
        try:
            socket_fd.sendall(header + packet)
        except Exception as e:
            print("here" + str(e))
        #gevent.sleep(0)

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
            
            print("recv len %d" % len(packet))

            if last_packet != None:
                print("reload packet data %d last packet %d" % (len(packet), len(last_packet)))
                packet = last_packet + packet
                last_packet = None
            start = 0
            while start < len(packet):
                client_fileno, client_state, content_len = struct.unpack("!IBH", packet[start : start + 7])
                if (content_len > len(packet[start + 7:])):
                    last_packet = packet[start:]
                    print("save packet %d" % len(packet[start:]))
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
                        print("fatal unknown atyp")
                        break
                    ip = gethostbyname(remote_addr)
                    port = int(remote_port)
                    try:
                        remote_socket = create_connection((ip, port), timeout=0.1)
                    except:
                        print("remote_socket create failed addr %s" % remote_addr)
                        continue
                    print("recv state 1 address %s fileno %d" % (remote_addr, client_fileno))
                    clients[client_fileno] = [remote_socket, 1]
                elif int(client_state) == 2:
                    print("recv state 2")
                    end = start + content_len
                    if clients.get(client_fileno) == None:
                        start = end
                        print("no fileno")
                        print(packet)
                        continue
                    print("recv and send state 2 fileno %d" % (client_fileno))
                    remote_socket = clients.get(client_fileno)[0]
                    remote_socket.sendall(packet[start : end])
                    start = end
                    if clients.get(client_fileno)[1] == 1:
                        clients.get(client_fileno)[1] = 2
                        gevent.spawn(remote_process, remote_socket, socket_fd, client_fileno)
                else:
                    print("fatal unknown client state")
                    break
            gevent.sleep(0)

def is_alive():
    while True:
        print("alive")
        gevent.sleep(5)

if __name__ == '__main__':
    gevent.spawn(is_alive)
    ForwardServer(forwader_address)
