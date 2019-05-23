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
class SkillRequestHandler(tornado.web.RequestHandler):
    SUPPORTED_METHOD = ('PUT','GET','DELETE')
    def prepare(self):
        self.worker = None
        self.others = set()
        self.filePath = None
        self.uuid = str(uuid.uuid4())
        self.set_status(200, "Initial statut")
        self.waitResponse = Condition()
        self.waitWorker = Condition()

        if self.request.method != 'POST' and self.request.method != 'PUT' and self.request.method != 'GET' and self.request.method != 'DELETE' :
            logging.debug("Received a non-POST / PUT / GET / DELTE request")
            self.error_server('Wrong request, server handles only POST, PUT, DELETE or GET requests')
        else:
            params=self.request.uri.split('/')
            if params[1] == 'intent':
                if self.request.method == 'POST' or self.request.method == 'PUT' :
                    #File Retrieval
                    # TODO: Adapt input to existing controller API
                    if 'txtFile' not in  self.request.files.keys():
                        logging.debug(self.request.method+" request does not contain 'txtFile' field.")
                        self.error_server(self.request.method+' request must contain a \'txtFile\' field.')
                    elif len(params) < 3:
                        logging.debug("POST request does not contain the skill name.")
                        self.error_server(self.request.method+' request must contain the skill name.')
                    else:
                        self.temp_file = self.request.files['txtFile'][0]['body']
                        self.skill_name = params[2].lower()
                elif self.request.method == 'GET' or self.request.method == 'DELETE':
                    if len(params) < 3:
                        logging.debug(self.request.method+" request does not contain the skill name.")
                        self.error_server(self.request.method+' request must contain the skill name.')
                    else:
                        logging.debug(params[2].lower())
                        self.skill_name = params[2].lower()
            else:
                if self.request.method != 'GET':
                    self.error_server('Wrong request, server handles only GET request')
                else:
                    self.skill_name = None

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
        self.worker.write_message(json.dumps({'uuid':self.uuid,'file': self.temp_file.encode('base64'), 'filename': self.skill_name, 'app':'skill', 'type':'post'}))
        yield self.waitResponse.wait()
        self.finish()

    @gen.coroutine
    def put(self, *args, **kwargs):
        logging.debug("Allocating Worker to %s" % self.uuid)
        yield self.allocate_worker()
        self.worker.write_message(json.dumps({'uuid':self.uuid,'file': self.temp_file.encode('base64'), 'filename': self.skill_name, 'app':'skill', 'type':'put'}))
        yield self.waitResponse.wait()
        self.finish()

    @gen.coroutine
    def delete(self, *args, **kwargs):
        logging.debug("Allocating Worker to %s" % self.uuid)
        yield self.allocate_worker()
        self.worker.write_message(json.dumps({'uuid':self.uuid, 'app':'skill', 'type':'delete', 'filename': self.skill_name}))
        yield self.waitResponse.wait()
        self.finish()

    @gen.coroutine
    def get(self, *args, **kwargs):
        logging.debug("Allocating Worker to %s" % self.uuid)
        yield self.allocate_worker()
        self.worker.write_message(json.dumps({'uuid':self.uuid, 'app':'skill', 'type':'get', 'filename': self.skill_name}))
        yield self.waitResponse.wait()
        self.finish()

    @gen.coroutine
    def free_other_workers(self):
        logging.debug("Free blocked workers")

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
