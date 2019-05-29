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



#LOADING CONFIGURATION
server_settings = configparser.ConfigParser()
server_settings.read('server.cfg')
TEMP_FILE_PATH = server_settings.get('machine_params', 'temp_file_location')


#Handler des requêtes de décodage.
class DecodeRequestHandler(tornado.web.RequestHandler):
    SUPPORTED_METHOD = ('POST')
    #Called at the beginning of a request before get/post/etc
    def prepare(self):
        self.worker = None
        self.filePath = None
        self.uuid = str(uuid.uuid4())
        self.set_status(200, "Initial statut")
        self.waitResponse = Condition()
        self.waitWorker = Condition()

        if self.request.method != 'POST':
            logging.debug("Received a non-POST request")
            self.set_status(403, "Worker failed to transcribe the audio")
            self.set_header("Content-Type", "application/json")
            self.set_header("Access-Control-Allow-Origin", "*")
            self.write({'transcript': {'error':'Wrong request, server handles only POST requests'}})
            self.waitResponse.notify()
            self.application.display_server_status()
            self.application.check_waiting_clients()
            self.finish()
        else:
            #File Retrieval
            # TODO: Adapt input to existing controller API
            if 'wavFile' not in  self.request.files.keys():
                self.set_status(403, "POST request must contain a 'file_to_transcript' field.")
                self.finish()
                logging.debug("POST request from %s does not contain 'file_to_transcript' field.")
            temp_file = self.request.files['wavFile'][0]['body']
            self.temp_file = temp_file
            #Writing file
            try:
                f = open(TEMP_FILE_PATH+self.uuid+'.wav', 'wb')
            except IOError:
                logging.error("Could not write file.")
                self.set_status(500, "Server error: Counldn't write file on server side.")
                self.finish()
            else:
               f.write(temp_file)
               self.filePath = TEMP_FILE_PATH+self.uuid+'.wav'
               logging.debug("File correctly received from client")


    @gen.coroutine
    def post(self, *args, **kwargs):
        logging.debug("Allocating Worker to %s" % self.uuid)

        yield self.allocate_worker()
        self.worker.write_message(json.dumps({'uuid':self.uuid,'file': self.temp_file.encode('base64'), 'app':'decode'}))
        yield self.waitResponse.wait()
        self.finish()

    @gen.coroutine
    def allocate_worker(self):
        while self.worker == None:
            try:
                self.worker = self.application.available_workers.pop()
            except:
                self.worker = None
                self.application.waiting_client.add(self)
                self.application.display_server_status()
                yield self.waitWorker.wait()
            else:
                self.worker.client_handler = self
                logging.debug("Worker allocated to client %s" % self.uuid)
                self.application.display_server_status()


    @gen.coroutine
    def send_message(self, message):
        self.set_status(200, "Worker has completed successfully")
        self.set_header("Content-Type", "application/json")
        self.set_header("Access-Control-Allow-Origin", "*")
        self.write({'transcript': message})
        self.application.num_requests_processed += 1
        self.waitResponse.notify()


    @gen.coroutine
    def send_error(self, message):
        self.set_status(503, "Worker failed to transcribe the audio")
        self.set_header("Content-Type", "application/json")
        self.set_header("Access-Control-Allow-Origin", "*")
        self.write({'transcript': message})
        self.application.num_requests_processed += 1
        self.waitResponse.notify()


    def on_finish(self):
        #CLEANUP
        pass
