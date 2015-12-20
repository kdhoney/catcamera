import string, cgi, time, io, picamera, socket, random
from os import curdir, sep
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
from SocketServer import ThreadingMixIn
from threading import Thread
from PIL import Image
import struct, StringIO
import ssl
import sys, re, threading, collections

from socket import *
from select import *
import sys
from time import ctime
import urllib2
import requests

import RPi.GPIO as GPIO
import json

cv = threading.Condition()

class ServerSocketThread(threading.Thread):
    def run(self):
        HOST = ''
        PORT = 8081
        BUFSIZE = 1024
        ADDR = (HOST, PORT)

        serverSocket = socket(AF_INET, SOCK_STREAM)
        serverSocket.bind(ADDR)

        serverSocket.listen(10)
        connection_list = [serverSocket]
        print 'start camera serverSocket. port : %s' % str(PORT)

        while connection_list:
            try:
                print "server socket wait connection"
                read_socket, write_socket, error_socket = select(connection_list, [], [], 10)
                for sock in read_socket:
                    if sock == serverSocket: #new client
                        clientSocket, addr_info = serverSocket.accept()
                        connection_list.append(clientSocket)
                        print "new connection"
                        socket_in_list = clientSocket
                        try:
                            print "clientSocket"
                            #socket_in_list.send('SU')
                        except Exception as e:
                            socket_in_list.close()
                            connection_list.remove(socket_in_list)
                    else: #receive from client
                        data = sock.recv(BUFSIZE).split(":")[0]
                        print "receive from client, command : ", data
                        socket_in_list = connection_list[-1]
                        if data == "ST":
                            #socket_in_list.send("STSU")
                            pass
                        elif data == "PS":
                            stream = ImageProcessor.getInstance().getStream_q()
                            filename = "imgTest.jpg"
                            ff = open(filename, 'w')
                            ff.write(stream)
                            ff.close()
                            url = 'http://52.27.20.131:8001/image_uploader/up/'
                            files = {'file':open(filename)}
                            r = requests.post(url, files=files)
                            print r
                            print "get data : ", data
                        else: #disconnected from client
                            connection_list.remove(sock)
                            sock.close()
                            print "disconnected from client"
            except KeyboardInterrupt:
                serverSocket.close()
                print "serverSocket Closed"
                #sys.exit()

class PIRSensorThread(threading.Thread):
    def run(self):
        GPIO.setmode(GPIO.BCM)
        PIR_PIN = 17
        GPIO.setup(PIR_PIN, GPIO.IN)

        pKey = "AIzaSyCY75G8uL0eqWWI_f3kRPdVpDr2H9C-s5Y"
        pRid = "APA91bESFezzPECK9Fz0DdhAfpSOOydr5Ln8YucaZpmE6aD8_yCwXr3Jt9l3l2n2wB_rYiwmMnE3sBoA6A4TQb_Z709REl7tS27xLSrhk3Cn0Wz2SNVf-_Xd9cz5areZMTZA5p4JPqdc"
        print "PIR Start (CTRL+C to exit)"
        time.sleep(1)
        print "ready"
        t_state = 0
        try:
            while True:
                gi = GPIO.input(PIR_PIN)
                if t_state == 0 and gi:
                    t_state = 1
                    msg = "Cat Detected!!"
                    values = {
                             'registration_ids': [pRid],
                             'collapse_key': "message",
                             'data': {"message": msg}
                             }
                    headers = {
                             'UserAgent': "GCM-Server",
                             'Content-Type': 'application/json',
                             'Authorization': "key=" + pKey,
                              }
                    response = requests.post("https://android.googleapis.com/gcm/send", data=json.dumps(values), headers = headers)
                    print response
                    print "cat detected"
                elif t_state == -1 and gi:
                    t_state = 1
                    print "detected continue"
                elif t_state >= 1:
                    t_state = t_state + 1
                    if t_state >= 16:
                        t_state = -1
                else:
                    t_state = 0
                    print "No detected"
                time.sleep(1)
        except KeyboardInterrupt:
            print "PIR Quit"
            GPIO.cleanup()


""" The RingBuffer class provides an implementation of a ring buffer
    for image data """
class RingBuffer(threading.Thread):

    # Initialize the buffer.
    def __init__(self, size_max):
        self.max = size_max
        self.data = collections.deque(maxlen=size_max)
        
    # Append an element to the ring buffer.
    def append(self, x):
        if len(self.data) == self.max:
            self.data.pop()
        self.data.append(x)

    # Retrieve the newest element in the buffer.
    def get(self):
        return self.data[-1]

""" The ImageProcessor class is a singleton implementation that wraps the
    interface of the Raspicam """
class ImageProcessor(threading.Thread):
    
    instance = None

    # Helper class for the singleton instance.
    class ImageProcessorHelper():
        def __call__(self, *args, **kw):
            # If an instance of singleton does not exist,
            # create one and assign it to singleton.instance
            if ImageProcessor.instance is None:
                ImageProcessor.instance = ImageProcessor()
            return ImageProcessor.instance

    getInstance = ImageProcessorHelper()

    # Initialization.
    def __init__(self):
        # Initialize an instance of the singleton class.
        if ImageProcessor.instance:
            raise RuntimeError, 'Only one instance of ImageProcessor is allowed!'
        
        ImageProcessor.instance = self
        super(ImageProcessor, self).__init__()
        self.isRecording = True
        self.timestamp = int(round(time.time() * 1000))
        self.semaphore = threading.BoundedSemaphore()
        self.camera = None
        self.prior_image = None
        self.stream = None
        self.buffer = RingBuffer(100)
        self.buffer_q = RingBuffer(100)
        self.upload_req = False
        self.start()

    # Run the video streaming thread within the singleton instace.
    def run(self):
        try:
            global cv
            if(self.camera == None):
                self.camera = picamera.PiCamera()
                self.camera.resolution = (176, 144)
                self.camera.framerate = 10
                self.camera.quality = 2
            time.sleep(2)
            print "Camera interface started..."
            stream = io.BytesIO()
            while True:
                for foo in self.camera.capture_continuous(stream, format='jpeg', use_video_port=True):
                    self.semaphore.acquire()
                    stream.seek(0)
                    self.buffer.append(stream.getvalue())
                    stream.truncate()
                    stream.seek(0)
                    self.semaphore.release()
                    if self.upload_req == True:
                        break
                    if int(round(time.time() * 1000)) - self.timestamp > 60000:
                        # Take the camera to sleep if it has not been used for
                        # 60 seconds.
                        print "No Client connected for 60 sec, camera set to sleep."
                        self.semaphore.acquire()
                        self.isRecording = False
                        self.semaphore.release()
                    if not self.isRecording:
                        break
                
                if self.upload_req == True:
                    cv.acquire()
                    self.upload_req = False
                    stream = io.BytesIO()
                    self.camera.resolution = (1056, 864)
                    self.camera.capture(stream, format='jpeg', use_video_port=True)
                    stream.seek(0)
                    self.buffer_q.append(stream.getvalue())
                    stream.truncate()
                    stream.seek(0)
                    self.camera.resolution = (176,144)
                    cv.notify()
                    cv.release()                    
                if not self.isRecording:
                    break
        finally:
            self.camera.stop_preview()
            self.camera.close()
            self.camera = None

    # Detect motion in the video stream.
    # FIXME: This has to be implemented more sophisticated.
    def detect_motion(self):
        stream = io.BytesIO()
        self.camera.capture(stream, format='jpeg', use_video_port=True)
        stream.seek(0)
        if self.prior_image is None:
            self.prior_image = Image.open(stream)
            return False
        else:
            current_image = Image.open(stream)
            # Compare the current image with the previous image to detect
            # motion.
            result = random.randint(0, 10) == 0
            self.prior_image = current_image
            return result

    # Get the latest image data from the MJPEG stream
    def getStream(self):
        self.timestamp = int(round(time.time() * 1000))
        if(self.isRecording == False):
            self.semaphore.acquire()
            self.isRecording = True
            self.semaphore.release()
            self.run()
        return self.buffer.get()

    def getStream_q(self):
        global cv
        self.timestamp = int(round(time.time() * 1000))
        if(self.isRecording == False):
            self.semaphore.acquire()
            self.isRecording = True
            self.semaphore.release()
            self.run()
        cv.acquire()
        self.upload_req = True
        cv.wait()
        cv.release()
        return self.buffer_q.get()


""" This class implements the request handler for the HTTP server. This class
    has to be passed to the ThreadedHTTPServer. """            
class RequestHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path.endswith("1.mjpeg"):
            self.send_response(200)
            self.send_header('Pragma:', 'no-cache');
            self.send_header('Cache-Control:', 'no-cache')
            self.send_header('Content-Encoding:', 'identify')
            self.send_header('Content-Type:', 'multipart/x-mixed-replace;boundary=--jpgboundary')
            self.end_headers()
            try:
                while 1:
                    stream = ImageProcessor.getInstance().getStream()
                    self.send_header('Content-type:','image/jpeg')
                    self.send_header('Content-length:', str(len(stream)))
                    self.end_headers()
                    self.wfile.write(stream)
                    self.wfile.write('--jpgboundary\r\n')
                    self.send_response(200)
                    time.sleep(0.02)
            except IOError as e:
                if hasattr(e, 'errno') and e.errno == 32:
                    print 'Error: broken pipe'
                    self.rfile.close()
                    return
                else:
                    raise e

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    ''' The threaded HTTP server '''

def main():
    try:
        ImageProcessor().getInstance()
        server = ThreadedHTTPServer(('0.0.0.0', 8080), RequestHandler)
        print 'HTTP server started...'
        server.serve_forever()
    except KeyboardInterrupt:
        print '^C key received, stopping the server'
        server.socket.close()
        
if __name__ == '__main__':
    socketThread = ServerSocketThread()
    PIRThread = PIRSensorThread()
    socketThread.start()     #start Server Socket Thread
    PIRThread.start()    #start PIR Sensor Thread
    main()
