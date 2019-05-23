#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
Created on Wed Jan  3 16:53:16 2018

@author: rbaraglia@linagora.com
@maintainer: irebai@linagora.com
"""
import os
import json
import functools
import threading
import uuid
import logging
import configparser

import tornado.ioloop
import tornado.web
import tornado.websocket
from tornado import gen
from tornado.locks import Condition

from DecodeRequest import *
from ModelRequest import *
from EntityRequest import *
from SkillRequest import *

#LOADING CONFIGURATION
server_settings = configparser.ConfigParser()
server_settings.read('server.cfg')
SERVER_PORT = server_settings.get('server_params', 'listening_port')
BUFFER_SIZE = server_settings.get('server_params', 'max_buffer_size')

TEMP_FILE_PATH = server_settings.get('machine_params', 'temp_file_location')
KEEP_TEMP_FILE = True if server_settings.get('server_params', 'keep_temp_files') == 'true' else False
LOGGING_LEVEL = logging.DEBUG if server_settings.get('server_params', 'debug') == 'true' else logging.INFO

if "OFFLINE_PORT" in os.environ:
    SERVER_PORT = os.environ['OFFLINE_PORT']

class Application(tornado.web.Application):
    def __init__(self):
        settings = dict(
            cookie_secret="43oETzKXQAGaYdkL5gEmGeJJFuYh7EQnp2XdTP1o/Vo=",
            template_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates"),
            static_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), "static"),
            xsrf_cookies=False,
            autoescape=None,
        )

        handlers = [
            (r"/", MainHandler),
            (r"/transcribe", DecodeRequestHandler),

            #Update the model
            (r"/model", ModelRequestHandler),

            #Create|Reset|Update|Delete|Get entity
            (r"/entity(/[^/]+){1}", EntityRequestHandler),
            (r"/entities",            EntityRequestHandler),

            #Add|Reset|Delete|Get intent
            (r"/intent(/[^/]+){1}", SkillRequestHandler),
            (r"/intents",             SkillRequestHandler),

            (r"/worker/ws/speech", WorkerWebSocketHandler)
        ]
        tornado.web.Application.__init__(self, handlers, **settings)
        self.connected_worker = 0
        self.available_workers = set()
        self.waiting_client = set()
        self.num_requests_processed = 0
        self.num_tot_workers = 0

    #TODO: Abort request when the client is waiting for a determined amount of time
    def check_waiting_clients(self):
        if len(self.waiting_client) > 0:
            try:
                client = self.waiting_client.pop()
            except:
                pass
            else:
                client.waitWorker.notify() 

    def display_server_status(self):
        logging.info('#'*50)
        logging.info("Connected workers: %s (Available: %s)" % (str(self.connected_worker),str(len(self.available_workers))))
        logging.info("Waiting clients: %s" % str(len(self.waiting_client)))
        logging.info("Requests processed: %s" % str(self.num_requests_processed))


# Return le README
class MainHandler(tornado.web.RequestHandler):
    def get(self):
        current_directory = os.path.dirname(os.path.abspath(__file__))
        parent_directory = os.path.join(current_directory, os.pardir)+'/../'
        readme = os.path.join(parent_directory, "README.md")
        self.set_header("Access-Control-Allow-Origin", "*")
        self.render(readme)

#WebSocket de communication entre le serveur et le worker
class WorkerWebSocketHandler(tornado.websocket.WebSocketHandler):
    def check_origin(self, origin):
        return True

    def open(self):
        self.client_handler = None
        self.application.available_workers.add(self)
        self.application.connected_worker += 1
        self.application.check_waiting_clients()
        logging.debug("Worker connected")
        self.application.display_server_status()
        self.application.num_tot_workers += 1

    def on_message(self, message):
        try:
            json_msg = json.loads(str(message))
        except:
            logging.debug("Error received from worker:" + message)
        else:
            if 'error' in json_msg.keys():
                self.client_handler.send_error(json_msg)
            else:
                self.client_handler.send_message(json_msg)

            if 'model' in json_msg.keys():
                self.client_handler.free_other_workers()

            self.client_handler = None
            self.application.available_workers.add(self)
            self.application.display_server_status()
            self.application.check_waiting_clients()

    def on_close(self):
        if self.client_handler != None:
            self.client_handler.set_status(503, "Worker failed")
            self.client_handler.finish()
        logging.debug("WORKER WebSocket closed")
        self.application.available_workers.discard(self)
        self.application.connected_worker -= 1
        self.application.display_server_status()

def main():
    logging.basicConfig(level=LOGGING_LEVEL, format="%(levelname)8s %(asctime)s %(message)s ")
    #Check if the temp_file repository exist
    if not os.path.isdir(TEMP_FILE_PATH):
        os.mkdir(TEMP_FILE_PATH)
    print('#'*50)
    app = Application()
    server = tornado.httpserver.HTTPServer(app, max_buffer_size=int(BUFFER_SIZE))
    server.listen(int(SERVER_PORT))
    logging.info('Starting up server listening on port %s' % SERVER_PORT)
    try:
        tornado.ioloop.IOLoop.instance().start()
    except KeyboardInterrupt:
        logging.info("Server close by user.")
if __name__ == '__main__':
    main()
