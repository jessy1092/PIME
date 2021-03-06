#! python3
import threading
import json
import sys
import os
from ctypes import *
from serviceManager import textServiceMgr


# import libpipe
dll_path = os.path.join(os.path.dirname(__file__), "libpipe.dll")
libpipe = CDLL(dll_path)

# define Win32 error codes for named pipe I/O
ERROR_MORE_DATA = 234
ERROR_IO_PENDING = 997


class Client:
    def __init__(self, server, pipe):
        self.pipe= pipe
        self.server = server
        self.service = None

    def init(self, msg):
        self.isWindows8Above = msg["isWindows8Above"]
        self.isMetroApp = msg["isMetroApp"]
        self.isUiLess = msg["isUiLess"]
        self.isUiLess = msg["isConsole"]

    def onActivate(self):
        pass

    def onDeactivate(self):
        if self.service:
            self.service.onDeactivate()
            self.service = None

    def onLangProfileActivated(self, guid):
        service = self.service
        # deactivate the current text service
        if service:
            service.onDeactivate()
        service = textServiceMgr.createService(self, guid)
        self.service = service
        # activate the new text service
        if service:
            service.onActivate()

    def onLangProfileDeactivated(self, guid):
        pass

    def handleRequest(self, msg): # msg is a json object
        success = True
        ret = None
        method = msg.get("method", None)
        seqNum = msg.get("seqNum", 0)
        print("handle message: ", threading.current_thread().name, method, seqNum)

        # these are messages handled by Client
        handled = True
        if method == "init":
            self.init(msg)
        elif method == "onActivate":
            self.onActivate()
        elif method == "onDeactivate":
            self.onDeactivate()
        elif method == "onLangProfileActivated":
            guid = msg["guid"]
            self.onLangProfileActivated(guid)
        elif method == "onLangProfileDeactivated":
            guid = msg["guid"]
            self.onLangProfileDeactivated(guid)
        else:
            handled = False

        reply = {}
        # these are messages handled by the text service
        service = self.service
        if service:
            if not handled: # if the request is not yet handled
                (success, ret) = service.handleRequest(method, msg)
            if success:
                reply = service.getReply()
            if ret != None:
                reply["return"] = ret
        reply["success"] = success
        reply["seqNum"] = seqNum # reply with sequence number added
        print("reply: ", reply)
        return reply


class ClientThread(threading.Thread):
    def __init__(self, client):
        threading.Thread.__init__(self)
        self.client = client
        self.buf = create_string_buffer(512)

    def run(self):
        client = self.client
        pipe = client.pipe
        server = client.server

        running = True
        while running:
            # Read client requests from the pipe.
            try:
                read_more = True
                msg = ""
                while read_more:
                    # read data from the pipe
                    error = c_ulong(0)
                    buf_len = c_ulong(512)
                    read_len = libpipe.read_pipe(pipe, self.buf, buf_len, pointer(error))
                    error = error.value
                    print("read: ", read_len, "error:", error)

                    # convert content in the read buffer to unicode
                    if read_len > 0:
                        data = self.buf.raw[:read_len]
                        data = data.decode("UTF-8")
                    else:
                        data = ""
                    # print("data: ", data)

                    if error == 0: # success
                        msg += data
                        read_more = False
                    elif error == ERROR_MORE_DATA:
                         msg += data
                    elif error == ERROR_IO_PENDING:
                         pass
                    else: # the pipe is broken
                        print("broken pipe")
                        running = False
                        read_more = False

                if msg:
                    # Process the incoming message.
                    msg = json.loads(msg) # parse the json input
                    # print("received msg", success, msg)

                    server.acquire_lock() # acquire a lock
                    reply = client.handleRequest(msg)
                    server.release_lock() # release the lock

                    if running:
                        reply = json.dumps(reply) # convert object to json

                        data = bytes(reply, "UTF-8") # convert to UTF-8
                        data_len = c_ulong(len(data))
                        print("write reply:", data_len)
                        libpipe.write_pipe(pipe, data, data_len, None)
                        print("written!!")
            except:
                import traceback
                # print callstatck to know where the exceptions is
                traceback.print_exc()

                print("exception!", sys.exc_info())
                break

        libpipe.close_pipe(pipe)
        server.remove_client(client)


class Server:
    def __init__(self):
        self.lock = threading.Lock()
        self.clients = []

    def acquire_lock(self):
        self.lock.acquire()

    def release_lock(self):
        self.lock.release()

    def run(self):
        while True:
            pipe = libpipe.connect_pipe(bytes("PIME", "UTF-8"))

            # client connected
            if pipe != -1:
                print("client connected")
                # create a Client instance for the client
                client = Client(self, pipe)
                self.lock.acquire()
                self.clients.append(client)
                self.lock.release()
                # run a separate thread for this client
                thread = ClientThread(client)
                thread.start()

        return True


    def remove_client(self, client):
        self.lock.acquire()
        self.clients.remove(client)
        print("client disconnected")
        self.lock.release()


def main():
    server = Server()
    server.run()


if __name__ == "__main__":
    main()
