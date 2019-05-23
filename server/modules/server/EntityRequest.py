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


#Handler des requêtes d'update. 
class EntityRequestHandler(tornado.web.RequestHandler):
    SUPPORTED_METHOD = ('POST','PUT','GET','DELETE')
    def prepare(self):
        self.set_header("Access-Control-Allow-Origin", "*")
        self.set_header('Access-Control-Allow-Headers','*')
        self.set_header('Access-Control-Allow-Methods', 'POST, GET, PUT, DELETE, OPTIONS')
        self.worker = None
        self.uuid = str(uuid.uuid4())
        self.set_status(200, "Initial statut")
        self.waitResponse = Condition()
        self.waitWorker = Condition()

        if self.request.method != 'POST' and self.request.method != 'PUT' and self.request.method and self.request.method != 'PATCH' and self.request.method != 'DELETE' and self.request.method != 'GET' :
            logging.debug("Received a non-POST / PUT / PATCH / DELETE / GET request")
            self.error_server('Wrong request, server handles only POST, PUT, PATCH, DELETE or GET requests')
        else:
            params=self.request.uri.split('/')
            if params[1] == 'entity':
                if self.request.method == 'POST' or self.request.method == 'PUT' or self.request.method == 'PATCH' :
                    #File Retrieval
                    # TODO: Adapt input to existing controller API
                    if 'txtFile' not in  self.request.files.keys():
                        logging.debug(self.request.method+" request does not contain 'txtFile' field.")
                        self.error_server(self.request.method+' request must contain a \'txtFile\' field.')
                    elif len(params) < 3:
                        logging.debug("POST request does not contain the entity name.")
                        self.error_server(self.request.method+' request must contain the entity name.')
                    else:
                        self.temp_file = self.request.files['txtFile'][0]['body']
                        self.entity_name = params[2].lower()
                elif self.request.method == 'GET' or self.request.method == 'DELETE':
                    if len(params) < 3:
                        logging.debug(self.request.method+" request does not contain the entity name.")
                        self.error_server(self.request.method+' request must contain the entity name.')
                    else:
                        self.entity_name = params[2].lower()
            else:
                if self.request.method != 'GET':
                    self.error_server('Wrong request, server handles only GET request')
                else:
                    self.entity_name = None


    def error_server(self, message):
        self.set_status(403, 'Worker failed')
        self.set_header("Content-Type", "application/json")
        self.set_header("Access-Control-Allow-Origin", "*")
        self.write({'Update': {'error':message}})
        self.waitResponse.notify()
        self.application.display_server_status()
        self.application.check_waiting_clients()
        self.finish()

    @gen.coroutine
    def post(self, *args, **kwargs):
        logging.debug("Allocating Worker to %s" % self.uuid)
        yield self.allocate_worker()
        self.worker.write_message(json.dumps({'uuid':self.uuid,'file': self.temp_file.encode('base64'), 'filename': self.entity_name, 'app':'entity', 'type':'post'}))
        yield self.waitResponse.wait()
        self.finish()

    @gen.coroutine
    def patch(self, *args, **kwargs):
        logging.debug("Allocating Worker to %s" % self.uuid)
        yield self.allocate_worker()
        self.worker.write_message(json.dumps({'uuid':self.uuid,'file': self.temp_file.encode('base64'), 'filename': self.entity_name, 'app':'entity', 'type':'patch'}))
        yield self.waitResponse.wait()
        self.finish()

    @gen.coroutine
    def put(self, *args, **kwargs):
        logging.debug("Allocating Worker to %s" % self.uuid)
        yield self.allocate_worker()
        self.worker.write_message(json.dumps({'uuid':self.uuid,'file': self.temp_file.encode('base64'), 'filename': self.entity_name, 'app':'entity', 'type':'put'}))
        yield self.waitResponse.wait()
        self.finish()

    @gen.coroutine
    def delete(self, *args, **kwargs):
        logging.debug("Allocating Worker to %s" % self.uuid)
        yield self.allocate_worker()
        self.worker.write_message(json.dumps({'uuid':self.uuid, 'app':'entity', 'type':'delete', 'filename': self.entity_name}))
        yield self.waitResponse.wait()
        self.finish()

    @gen.coroutine
    def get(self, *args, **kwargs):
        logging.debug("Allocating Worker to %s" % self.uuid)
        yield self.allocate_worker()
        self.worker.write_message(json.dumps({'uuid':self.uuid, 'app':'entity', 'type':'get', 'filename': self.entity_name}))
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
        self.write({self.request.method: message})
        self.application.num_requests_processed += 1
        self.waitResponse.notify()

    @gen.coroutine
    def send_error(self, message):
        self.set_status(503, "Worker failed")
        self.set_header("Content-Type", "application/json")
        self.set_header("Access-Control-Allow-Origin", "*")
        self.write({self.request.method: message})
        self.application.num_requests_processed += 1
        self.waitResponse.notify()

    def on_finish(self):
        #CLEANUP
        pass
