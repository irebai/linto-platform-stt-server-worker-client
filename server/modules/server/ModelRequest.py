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
class ModelRequestHandler(tornado.web.RequestHandler):
    SUPPORTED_METHOD = ('POST')
    def prepare(self):
        self.worker = None
        self.others = set()
        self.uuid = str(uuid.uuid4())
        self.set_status(200, "Initial statut")
        self.waitResponse = Condition()
        self.waitWorker = Condition()

        if self.request.method != 'POST' and self.request.method != 'GET' :
            logging.debug("Received a non-POST and a non-GET request")
            self.error_server('Wrong request, server handles only POST or GET requests')

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
        yield self.stop_all_workers()
        self.worker.write_message(json.dumps({'uuid':self.uuid, 'app':'model', 'type':'update'}))
        yield self.waitResponse.wait()
        self.finish()

    @gen.coroutine
    def get(self, *args, **kwargs):
        logging.debug("Allocating Worker to %s" % self.uuid)
        yield self.allocate_worker()
        self.worker.write_message(json.dumps({'uuid':self.uuid, 'app':'model', 'type':'get'}))
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
    def stop_all_workers(self):
        while len(self.others) != self.application.num_tot_workers:
            try:
                self.others.add(self.application.available_workers.pop())
            except:
                self.worker = None
                self.application.waiting_client.add(self)
                self.application.display_server_status()
                logging.debug("Waiting until all workers become free")
                yield self.waitWorker.wait()

        logging.debug("Blocked workers: %s" % str(len(self.others)))
        self.worker = self.others.pop()
        self.worker.client_handler = self
        logging.debug("Worker allocated to client %s" % self.uuid)
        self.application.display_server_status()

    @gen.coroutine
    def free_other_workers(self):
        logging.debug("Free blocked workers: %s" % str(len(self.others)))
        for worker in self.others:
            self.application.available_workers.add(worker)

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
