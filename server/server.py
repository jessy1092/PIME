from win32api import *
from win32pipe import *
from win32security import *
from win32event import *
from win32file import *
from winerror import *
from win32con import * # for VK_XXX constants
import threading
import json
import sys


class KeyEvent:
    def __init__(self, msg):
        self.charCode = msg["charCode"]
        self.keyCode = msg["keyCode"]
        self.repeatCount = msg["repeatCount"]
        self.scanCode = msg["scanCode"]
        self.isExtended = msg["isExtended"]
        self.keyStates = msg["keyStates"]

    def isKeyDown(self, code):
        return (self.keyStates[code] & (1 << 7)) != 0

    def isKeyToggled(self, code):
        return (self.keyStates[code] & 1) != 0


class TextService:
    def __init__(self, client):
        self.client = client

    def init(self, msg):
        self.id = msg["id"]
        self.isWindows8Above = msg["isWindows8Above"]
        self.isMetroApp = msg["isMetroApp"]
        self.isUiLess = msg["isUiLess"]
        self.isUiLess = msg["isConsole"]
        self.keyboardOpen = False
        self.isComposing = False
        self.showCandidates = False

    def updateStatus(self, msg):
        if "keyboardOpen" in msg
            self.keyboardOpen = msg["keyboardOpen"]
        if "isComposing" in msg
            self.keyboardOpen = msg["isComposing"]
        if "showCandidates" in msg
            self.keyboardOpen = msg["showCandidates"]

    # methods that should be implemented by derived classes
    def onActivate(self):
        pass

    def onDeactivate(self):
        pass

    def filterKeyDown(self, keyEvent):
        return False

    def onKeyDown(self, keyEvent):
        return False

    def filterKeyUp(self, keyEvent):
        return False

    def onKeyUp(self, keyEvent):
        return False

    def onCommand(self):
        pass

    def onCompartmentChanged(self):
        pass

    def onKeyboardStatusChanged(self):
        pass

    # public methods that should not be touched
    def langBarStatus(self):
        pass

    # language bar buttons
    def addButton(self, button):
        pass

    def removeButton(self, button):
        pass

    # preserved keys
    def addPreservedKey(self, keyCode, modifiers, guid):
        pass

    def removePreservedKey(self, guid):
        pass

    # is keyboard disabled for the context (NULL means current context)
    # bool isKeyboardDisabled(ITfContext* context = NULL);

    # is keyboard opened for the whole thread
    def isKeyboardOpened(self):
        return self.keyboardOpen

    def setKeyboardOpen(self, kb_open):
        self.keyboardOpen = kb_open

    def startComposition(self):
        self.isComposing = True

    def endComposition(self):
        self.isComposing = False

    def setCompositionString(self, s):
        self.compositionString = s

    def setCompositionCursor(self, pos):
        self.compositionCursor = s

    def setCommitString(self, s):
        self.commitString = s

    def setCandidateList(self, cand):
        self.candidateList = cand



class DemoTextService(TextService):
    def __init__(self, client):
        TextService.__init__(self, client)

    def onActivate(self):
        pass

    def onDeactivate(self):
        pass

    def filterKeyDown(self, keyEvent):
        if keyEvent.isKeyToggled(VK_CAPITAL):
            return False
        return True

    def onKeyDown(self, keyEvent):
        if keyEvent.isKeyToggled(VK_CAPITAL):
            return False
        return True

    def filterKeyUp(self, keyEvent):
        return False

    def onKeyUp(self, keyEvent):
        return False

    def onKeyboardStatusChanged(self):
        pass




class Client:
    def __init__(self, server, pipe):
        self.pipe= pipe
        self.server = server
        self.service = DemoTextService(self) # FIXME: allow different types of services here


    def handle_request(self, msg): # msg is a json object
        success = True
        reply = dict()
        ret = None
        method = msg["method"]
        print("handle message: ", method)

        service = self.service
        service.updateStatus(msg)

        if method == "init":
            service.init(msg)
        elif method == "onActivate":
            service.onActivate()
        elif method == "onDeactivate":
            service.onDeactivate()
        elif method == "filterKeyDown":
            keyEvent = KeyEvent(msg)
            ret = service.filterKeyDown(keyEvent)
        elif method == "onKeyDown":
            keyEvent = KeyEvent(msg)
            ret = service.onKeyDown(keyEvent)
        elif method == "filterKeyUp":
            keyEvent = KeyEvent(msg)
            ret = service.filterKeyUp(keyEvent)
        elif method == "onKeyUp":
            keyEvent = KeyEvent(msg)
            ret = service.onKeyUp(keyEvent)
        elif method == "onPreservedKey":
            ret = service.onPreservedKey()
        elif method == "onCommand":
            service.onCommand()
        elif method == "onCompartmentChanged":
            service.onCompartmentChanged()
        elif method == "onKeyboardStatusChanged":
            service.onKeyboardStatusChanged()
        elif method == "onCompositionTerminated":
            service.onCompositionTerminated()
        elif method == "onLangProfileActivated":
            pass
        elif method == "onLangProfileDeactivated":
            pass
        reply["success"] = success
        if ret != None:
            reply["return"] = ret
        return reply



class ClientThread(threading.Thread):
    def __init__(self, client):
        threading.Thread.__init__(self)
        self.client = client
        self.buf = AllocateReadBuffer(512)

    def run(self):
        client = self.client
        pipe = client.pipe
        server = client.server

        running = True
        while running:
            # Read client requests from the pipe.
            # http://docs.activestate.com/activepython/3.3/pywin32/win32file__ReadFile_meth.html
            try:
                read_more = True
                msg = ''
                while read_more:
                    (success, data) = ReadFile(pipe, self.buf, None)
                    data = data.decode("UTF-8")
                    # print("data: ", data)
                    if success == 0: # success
                        msg += data
                        read_more = False
                    elif success == ERROR_MORE_DATA:
                        msg += data
                    elif success == ERROR_IO_PENDING:
                        pass
                    else: # the pipe is broken
                        print("broken pipe")
                        running = False

                # Process the incoming message.
                msg = json.loads(msg) # parse the json input
                # print("received msg", success, msg)

                server.acquire_lock() # acquire a lock
                reply = client.handle_request(msg)
                server.release_lock() # release the lock

                reply = json.dumps(reply) # convert object to json
                WriteFile(pipe, bytes(reply, "UTF-8"), None)
            except:
                print("exception!", sys.exc_info())
                break

        FlushFileBuffers(pipe)
        DisconnectNamedPipe(pipe)
        CloseHandle(pipe)
        server.remove_client(client)


# https://msdn.microsoft.com/en-us/library/windows/desktop/aa365588(v=vs.85).aspx
class Server:

    def __init__(self):
        self.lock = threading.Lock()
        self.clients = []


    # This function creates a pipe instance and connects to the client.
    def create_pipe(self):
        name = "\\\\.\\pipe\\mynamedpipe"
        sa = SECURITY_ATTRIBUTES()
        buffer_size = 1024
        sa = None
        # create the pipe
        pipe = CreateNamedPipe(name,
                               PIPE_ACCESS_DUPLEX,
                               PIPE_TYPE_MESSAGE|PIPE_READMODE_MESSAGE|PIPE_WAIT,
                               PIPE_UNLIMITED_INSTANCES,
                               buffer_size,
                               buffer_size,
                               NMPWAIT_USE_DEFAULT_WAIT,
                               sa)
        return pipe


    def acquire_lock(self):
        self.lock.acquire()


    def release_lock(self):
        self.lock.release()


    def run(self):
        while True:
            pipe = self.create_pipe()
            if pipe == INVALID_HANDLE_VALUE:
                return False

            print("pipe created, wait for client")
            # Wait for the client to connect; if it succeeds, the function returns a nonzero value.
            # If the function returns zero, GetLastError returns ERROR_PIPE_CONNECTED.
            # According to Windows API doc, ConnectNamedPipe() returns non-zero on success.
            # However, the doc of pywin32 stated that it should return zero instead. :-(
            connected = (ConnectNamedPipe(pipe, None) == 0)
            if not connected:
                connected = (GetLastError() == ERROR_PIPE_CONNECTED)

            if connected: # client connected
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
    server.close()

if __name__ == "__main__":
    main()