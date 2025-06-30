from json import dumps, loads
from socket import AF_INET, SOCK_STREAM, socket
import time

from xbmcgui import Dialog
import xbmc

from syncplay.util import gs, gsi

# This is literally connected instantly, just keep it None for a bit.
sock: socket = None  # type: ignore
_connected = False

def connect():
    global sock, _connected
    
    try:
        if sock:
            try:
                sock.close()
            except:
                pass
        
        sock = socket(AF_INET, SOCK_STREAM)
        sock.settimeout(10)  # 10 second timeout for connection
        sock.connect((gs("address"), gsi("port")))
        _connected = True
        xbmc.log("Syncplay: Successfully connected to server", xbmc.LOGINFO)
        return True
    except Exception as e:
        xbmc.log(f"Syncplay: Connection failed: {str(e)}", xbmc.LOGERROR)
        Dialog().notification("Couldn't connect to syncplay",
                            "Request timed out; wrong server information?")
        _connected = False
        sock = None
        return False

def disconnect():
    global sock, _connected
    if sock:
        try:
            sock.close()
        except:
            pass
        finally:
            sock = None
            _connected = False

def is_connected():
    return _connected and sock is not None

def reconnect():
    """Attempt to reconnect to the server"""
    xbmc.log("Syncplay: Attempting to reconnect...", xbmc.LOGINFO)
    disconnect()
    time.sleep(1)  # Brief delay before reconnecting
    return connect()

def receive():
    global sock, _connected
    
    if not is_connected():
        if not reconnect():
            return []
    
    try:
        # Set a timeout for receiving data
        sock.settimeout(5)
        # 4096 seems like a decent power of two. Might change this later (very low possibility).
        # Cuts off the last string because its blank.
        data = sock.recv(4096).decode("utf-8").split("\r\n")[:-1]
        retdat = []
        for line in data:
            if line.strip():  # Skip empty lines
                try:
                    line = loads(line)
                    retdat.append(line)
                except Exception as e:
                    xbmc.log(f"Syncplay: Failed to parse JSON: {line} - Error: {str(e)}", xbmc.LOGWARNING)
        return retdat
    
    except OSError as e:
        if e.errno == 9:  # Bad file descriptor
            xbmc.log("Syncplay: Socket closed unexpectedly, attempting to reconnect", xbmc.LOGWARNING)
            _connected = False
            if reconnect():
                return receive()  # Try again after reconnection
        else:
            xbmc.log(f"Syncplay: Socket error in receive(): {str(e)}", xbmc.LOGERROR)
        return []
    
    except Exception as e:
        xbmc.log(f"Syncplay: Unexpected error in receive(): {str(e)}", xbmc.LOGERROR)
        _connected = False
        return []

def send(data: dict):
    global sock, _connected
    
    if not is_connected():
        if not reconnect():
            xbmc.log("Syncplay: Cannot send data - not connected", xbmc.LOGWARNING)
            return False
    
    try:
        # Compact encoding
        jsondat = dumps(data, separators=(",", ":"))
        # Uses \r\n by default. Why?
        sock.sendall((jsondat + "\r\n").encode("utf-8"))
        return True
        
    except BrokenPipeError as e:
        xbmc.log(f"Syncplay: Broken pipe error - server disconnected: {str(e)}", xbmc.LOGWARNING)
        _connected = False
        # Attempt to reconnect and resend
        if reconnect():
            try:
                jsondat = dumps(data, separators=(",", ":"))
                sock.sendall((jsondat + "\r\n").encode("utf-8"))
                return True
            except Exception as retry_e:
                xbmc.log(f"Syncplay: Failed to resend after reconnect: {str(retry_e)}", xbmc.LOGERROR)
        return False
        
    except OSError as e:
        xbmc.log(f"Syncplay: Socket error in send(): {str(e)}", xbmc.LOGERROR)
        _connected = False
        return False
        
    except Exception as e:
        xbmc.log(f"Syncplay: Unexpected error in send(): {str(e)}", xbmc.LOGERROR)
        return False

# Initialize connection
if not connect():
    xbmc.log("Syncplay: Initial connection failed", xbmc.LOGERROR)
