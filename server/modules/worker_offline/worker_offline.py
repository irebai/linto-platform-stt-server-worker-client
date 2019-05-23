#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Jan  3 17:10:23 2018
Updated on Wed Sep 12 15:18:00 2018

@author: rbaraglia@linagora.com
@maintainer: irebai@linagora.com
"""

import os
import argparse
import threading
import logging
import json
import subprocess
import configparser
import re
import tenacity
import base64
import locale
locale.setlocale(locale.LC_ALL, 'fr_FR.utf8')
from shutil import copyfile
from shutil import rmtree

from ws4py.client.threadedclient import WebSocketClient

#LOADING CONFIGURATION
worker_settings = configparser.ConfigParser()
worker_settings.read('/opt/worker.config')
SERVER_IP = worker_settings.get('server_params', 'server_ip')
SERVER_PORT = worker_settings.get('server_params', 'server_port')
SERVER_TARGET = worker_settings.get('server_params', 'server_target')
INDICE_DATA = True if worker_settings.get('worker_params', 'confidence_score') == 'true' else False
HCLG_MODE = worker_settings.get('worker_params', 'hclg_mode')

#Decoder parameters applied for both GMM and DNN based ASR systems
decoder_settings = configparser.ConfigParser()
decoder_settings.read('/opt/models/AM/decode.cfg')
DECODER_SYS = decoder_settings.get('decoder_params', 'decoder')
DECODER_MINACT = decoder_settings.get('decoder_params', 'min_active')
DECODER_MAXACT = decoder_settings.get('decoder_params', 'max_active')
DECODER_BEAM = decoder_settings.get('decoder_params', 'beam')
DECODER_LATBEAM = decoder_settings.get('decoder_params', 'lattice_beam')
DECODER_ACWT = decoder_settings.get('decoder_params', 'acwt')
DECODER_FSF = decoder_settings.get('decoder_params', 'frame_subsampling_factor')

AMPATH = decoder_settings.get('decoder_params', 'ampath')
LMGenPATH = decoder_settings.get('decoder_params', 'lmPath')
NGRAMS = decoder_settings.get('decoder_params', 'lmOrder')

if "OFFLINE_PORT" in os.environ:
    SERVER_PORT = os.environ['OFFLINE_PORT']

AM_FINAL_PATH="/opt/models/AM/"+AMPATH
LM_FINAL_PATH="/opt/models/LM/"
LMGen_FINAL_PATH="/opt/models/AM/"+LMGenPATH
TEMP_FILE_PATH="/opt/tmpfiles/"
TEMP_LM_PATH="/opt/tmplm/"
AM_CONFIG_PATH="/opt/models/"

SKILL_PATH=LM_FINAL_PATH+"/skills/"
ENTITY_PATH=LM_FINAL_PATH+"/entities/"
if not os.path.isdir(SKILL_PATH):
    os.mkdir(SKILL_PATH)
if not os.path.isdir(ENTITY_PATH):
    os.mkdir(ENTITY_PATH)

#Prepare config files
with open(AM_FINAL_PATH+"/conf/online.conf") as f:
    values = f.readlines()
    with open(AM_CONFIG_PATH+"/online.conf", 'w') as f:
        for i in values:
            f.write(i)
        f.write("--ivector-extraction-config="+AM_CONFIG_PATH+"/ivector_extractor.conf\n")
        f.write("--mfcc-config="+AM_FINAL_PATH+"/conf/mfcc.conf")

with open(AM_FINAL_PATH+"/conf/ivector_extractor.conf") as f:
    values = f.readlines()
    with open(AM_CONFIG_PATH+"/ivector_extractor.conf", 'w') as f:
        for i in values:
            f.write(i)
        f.write("--splice-config="+AM_FINAL_PATH+"/conf/splice.conf\n")
        f.write("--cmvn-config="+AM_FINAL_PATH+"/conf/online_cmvn.conf\n")
        f.write("--lda-matrix="+AM_FINAL_PATH+"/ivector_extractor/final.mat\n")
        f.write("--global-cmvn-stats="+AM_FINAL_PATH+"/ivector_extractor/global_cmvn.stats\n")
        f.write("--diag-ubm="+AM_FINAL_PATH+"/ivector_extractor/final.dubm\n")
        f.write("--ivector-extractor="+AM_FINAL_PATH+"/ivector_extractor/final.ie")



class NoRouteException(Exception):
    pass
class ConnexionRefusedException(Exception):
    pass

class WorkerWebSocket(WebSocketClient):
    def __init__(self, uri):
        WebSocketClient.__init__(self, url=uri, heartbeat_freq=10)

    def opened(self):
        pass
    def guard_timeout(self):
        pass
    def received_message(self, m):
        try:
            json_msg = json.loads(str(m))
        except:
            logging.debug("Message received: %s" % str(m))
        else:
############################################################################################################################
############ Speech decode API
            if 'uuid' in json_msg.keys() and 'app' in json_msg.keys() and json_msg['app'] == 'decode':
                self.client_uuid = json_msg['uuid']
                self.fileName = self.client_uuid.replace('-', '')
                self.file = base64.b64decode(json_msg['file'])
                self.filepath = TEMP_FILE_PATH+self.fileName+".wav"
                with open(self.filepath, 'wb') as f:
                    f.write(self.file)
                logging.debug("FileName received: %s" % self.filepath)

                # Signal processing
                logging.debug("sox processing")
                subprocess.call("sox "+self.filepath+" -t wav -b 16 -r 16000 -c 1 "+self.filepath+"_tmp.wav; mv "+self.filepath+"_tmp.wav "+self.filepath, shell=True);

                # Offline decoder call
                logging.debug("Offline decoder call")
                subprocess.call("scripts/decode.sh --decoder "+DECODER_SYS+" --tmpdir "+TEMP_FILE_PATH+" --online_conf "+AM_CONFIG_PATH+"/online.conf "+AM_FINAL_PATH+" "+LM_FINAL_PATH+" "+self.filepath+" "+DECODER_MINACT+" "+DECODER_MAXACT+" "+DECODER_BEAM+" "+DECODER_LATBEAM+" "+DECODER_ACWT+" "+DECODER_FSF, shell=True)

                # Check result
                if os.path.isfile(TEMP_FILE_PATH+'/decode.log'):
                    try:
                         with open(TEMP_FILE_PATH+'/decode.log', 'r', encoding='utf-8') as resultFile:
                             result = resultFile.read().strip()
                             self.send_result(result)
                    except Exception as e:
                         self.send_result("")
                else:
                    logging.error("Worker Failed to create transcription file")
                    self.send_result("")

                # Delete temporary files
                #for file in os.listdir(TEMP_FILE_PATH):
                 #   os.remove(TEMP_FILE_PATH+file)

############################################################################################################################
############ Update the language model
            elif 'uuid' in json_msg.keys() and 'app' in json_msg.keys() and json_msg['app'] == 'model':
                self.client_uuid = json_msg['uuid']
                self.skill_dir   = SKILL_PATH
                self.entity_dir  = ENTITY_PATH
                self.skill_json = self.skill_dir+'/data.json'
                self.entity_json = self.entity_dir+'/data.json'
                self.mode = json_msg['type']

                if self.mode == 'get':

                    cmds=[] #prepare the set of commands
                    try:
                        with open(self.skill_json) as f: #load the list of skills
                            skills = json.load(f)
                    except:
                        msg = json.dumps({u'uuid': self.client_uuid, u'get':'No intent has been found'})
                    else:
                        for skill in skills['intents']: #load all skills
                            self.skill_file = self.skill_dir+'/'+skill
                            with open(self.skill_file, 'r', encoding='utf-8') as f: #load each skill
                                txt = f.readlines()
                            cmds = list(cmds + txt)
                        cmds = {'commands' : list(map(lambda s: s.strip(), cmds))}
                        msg = json.dumps({u'uuid': self.client_uuid, u'get':cmds})
                else:
                    test,msg=self.prepare_HCLG(LMGen_FINAL_PATH)
                    if test:
                        # call of language model generation
                        logging.debug("Update HCLG graph.")
                        subprocess.call("cd scripts; ./prepare_HCLG"+HCLG_MODE+".sh --order "+NGRAMS+" "+AM_FINAL_PATH+" "+LM_FINAL_PATH+" "+LMGen_FINAL_PATH+" "+TEMP_LM_PATH, shell=True)
                        # Check result
                        if os.path.isfile(TEMP_LM_PATH+'update.log'):
                            with open(TEMP_LM_PATH+'update.log', 'r', encoding='utf-8') as resultFile:
                                result = resultFile.read().strip()
                                logging.debug("Update status : %s" % result)
                                data = json.loads(result)
                                if 'update' in data.keys():
                                    if 'oov' in data.keys():
                                        oov = data['oov'].split(',')
                                        oov = list(set(list(filter(None, oov))))
                                        logging.debug(oov)
                                        msg = {'status':data['update'], 'warning' : 'Please check the speeling of the detected out-of-vocabulary words.', 'oov':list(map(lambda s: s.strip(), oov))}
                                        msg = json.dumps({u'uuid': self.client_uuid, u'model':msg})
                                    else:
                                        msg = json.dumps({u'uuid': self.client_uuid, u'model':data['update']})
                                elif 'error' in data.keys():
                                    msg = json.dumps({u'uuid': self.client_uuid, u'error':data['error']})
                                else:
                                    msg = json.dumps({u'uuid': self.client_uuid, u'error':"Unknown problem"})
                        else:
                            msg = json.dumps({u'uuid': self.client_uuid, u'error':"Unknown problem"})
                self.send(msg)

############################################################################################################################
############ Update Entity (add/reset entity to the repository)
            elif 'uuid' in json_msg.keys() and 'app' in json_msg.keys() and json_msg['app'] == 'entity':
                self.mode = json_msg['type']
                self.client_uuid = json_msg['uuid']
                self.entity = json_msg['filename']
                self.entity_dir  = ENTITY_PATH
                self.entity_json = self.entity_dir+'/data.json'
                logging.debug(locale.getlocale())

                #Return either the list of entities or the values of a given entity name
                if self.mode == 'get': 
                    if self.entity == None:
                        try:
                            with open(self.entity_json) as f: #load the list of entities
                                entities = json.load(f)
                            msg = json.dumps({u'uuid': self.client_uuid, u'get':entities})
                        except:
                            msg = json.dumps({u'uuid': self.client_uuid, u'get':'No entity has been found'})
                    else:
                        #prepare lexicon
                        lexicon={}
                        if os.path.isfile(LMGen_FINAL_PATH+'/dict/lexicon.txt'):
                            with open(LMGen_FINAL_PATH+'/dict/lexicon.txt') as f: #load lexicon
                                lex = f.readlines()
                            for e in lex:
                                e = e.strip().split('\t')
                                if len(e) > 1:
                                    lexicon[e[0]]=e[1]
                                else:
                                    e = e.strip().split(' ')
                                    lexicon[e[0]]=' '.join(e[1:])
                        try:
                            with open(self.entity_dir+'/'+self.entity, 'r', encoding='utf-8') as f: #load the requested entity
                                values = f.readlines()

                            txt = self.transform_entity(self.entity, list(map(lambda s: s.strip(), values)), lexicon) #Normalize the entity
                            logging.debug(txt) #print normalized entity for debug

                            values = {self.entity : list(map(lambda s: s.strip(), values))}
                            msg = json.dumps({u'uuid': self.client_uuid, u'get':values})
                        except:
                            msg = json.dumps({u'uuid': self.client_uuid, u'get':'Could not find the given entity name'})
                
                #Remove the entity from the entity repository
                elif self.mode == 'delete':
                    try:
                        with open(self.entity_json) as f: #load the 'data.json'
                            entities = json.load(f)
                        if os.path.isfile(self.entity_dir+'/'+self.entity):
                            os.remove(self.entity_dir+'/'+self.entity) #remove the entity file from the repository
                        if self.entity in entities['entities']: #check if the entity exists in the data.json
                            entities['entities'].remove(self.entity) #remove the entity from the data.json object
                            with open(self.entity_json, 'w') as outfile: #save the new data.json object
                                json.dump(entities, outfile, sort_keys=True, indent=4)
                            msg = json.dumps({u'uuid': self.client_uuid, u'delete':'The entity \''+self.entity+'\' is successfully removed'})
                        else:
                            msg = json.dumps({u'uuid': self.client_uuid, u'error':'Could not find the given entity name'})
                    except:
                        msg = json.dumps({u'uuid': self.client_uuid, u'error':'The entity does not exist'})
                        logging.debug('File '+self.entity_json+' does not exist')
                
                #POST | PUT | PATCH requests
                else:
                    self.file = base64.b64decode(json_msg['file']) #read buffer
                    self.entity_file = self.entity_dir+'/'+self.entity
                    logging.debug("Entity Name received: %s" % self.entity)

                    try:
                        with open(self.entity_json) as f: #load the list of entities
                            entities = json.load(f)
                    except:
                        logging.debug('File '+self.entity_json+' does not exist')
                        entities = {'entities':[]} #Create a list if it's not yet created


                    #create the entity 'error if exist'
                    if self.mode == 'post':
                        if not self.entity in entities['entities']:
                            with open(self.entity_file, 'wb') as f: #save the buffer
                                f.write(self.file)
                            entities['entities'].append(self.entity) #add the entity to the list
                            with open(self.entity_json, 'w') as outfile: #save data.json file
                                json.dump(entities, outfile, sort_keys=True, indent=4)
                            msg = json.dumps({u'uuid': self.client_uuid, u'create':'The entity \''+self.entity+'\' is successfully created'})
                        else:
                            msg = json.dumps({u'uuid': self.client_uuid, u'error':'The entity already exists'})


                    #replace the entity 'error if does not exist'
                    elif self.mode == 'put':
                        if self.entity in entities['entities']:
                            with open(self.entity_file, 'wb') as f: #save the buffer
                                f.write(self.file)
                            msg = json.dumps({u'uuid': self.client_uuid, u'reset':'The entity \''+self.entity+'\' is successfully replaced'})
                        else:
                            msg = json.dumps({u'uuid': self.client_uuid, u'error':'The entity does not exist'})


                    #update the entity 'error if does not exist'
                    elif self.mode == 'patch':
                        if self.entity in entities['entities']:
                            with open(self.entity_file, 'ab') as f: #save the buffer
                                f.write(self.file)
                            msg = json.dumps({u'uuid': self.client_uuid, u'update':'The entity \''+self.entity+'\' is successfully replaced'})
                        else:
                            msg = json.dumps({u'uuid': self.client_uuid, u'error':'The entity does not exist'})

                self.send(msg)


############################################################################################################################
############ Update Skill and language model (add/delete skill to the repository)
            elif 'uuid' in json_msg.keys() and 'app' in json_msg.keys() and json_msg['app'] == 'skill':
                self.mode = json_msg['type']
                self.client_uuid = json_msg['uuid']
                self.skill = json_msg['filename']
                self.skill_dir  = SKILL_PATH
                self.skill_json = self.skill_dir+'/data.json'

                #Return either the list of entities or the values of a given skill name
                if self.mode == 'get': 
                    if self.skill == None:
                        try:
                            with open(self.skill_json) as f: #load the list of entities
                                intents = json.load(f)
                            msg = json.dumps({u'uuid': self.client_uuid, u'get':intents})
                        except:
                            msg = json.dumps({u'uuid': self.client_uuid, u'get':'No intent has been found'})
                    else:
                        #prepare the words
                        words={}
                        if os.path.isfile(LMGen_FINAL_PATH+'/dict/lexicon.txt'):
                            with open(LMGen_FINAL_PATH+'/dict/lexicon.txt') as f: #load lexicon
                                lex = f.readlines()
                            for e in lex:
                                if '-' in e:
                                    e = e.strip().split('\t')
                                    if len(e) == 1:
                                        e = e.strip().split(' ')
                                    w=e[0].strip()
                                    words[re.sub(r'-',' ',w)]=w
                        try:
                            with open(self.skill_dir+'/'+self.skill, 'r', encoding='utf-8') as f: #load the requested skill
                                values = f.readlines()

                            txt = self.transform_skill(self.skill, list(map(lambda s: s.strip(), values)), words) #Normalize the intent commands
                            logging.debug(txt) #print normalized commands for debug

                            values = {self.skill : list(map(lambda s: s.strip(), values))}
                            msg = json.dumps({u'uuid': self.client_uuid, u'get':values})
                        except Exception as e:
                            logging.debug(e)
                            msg = json.dumps({u'uuid': self.client_uuid, u'get':'Could not find the given intent name'})

                #Remove the skill from the skill repository
                elif self.mode == 'delete':
                    try:
                        with open(self.skill_json) as f: #load the 'data.json'
                            skills = json.load(f)
                        if os.path.isfile(self.skill_dir+'/'+self.skill):
                            os.remove(self.skill_dir+'/'+self.skill) #remove the skill file from the repository
                        if self.skill in skills['intents']: #check if the skill exists in the data.json
                            skills['intents'].remove(self.skill) #remove the skill from the data.json object
                            with open(self.skill_json, 'w') as outfile: #save the new data.json object
                                json.dump(skills, outfile, sort_keys=True, indent=4)
                            msg = json.dumps({u'uuid': self.client_uuid, u'delete':'The intent \''+self.skill+'\' is successfully removed'})
                        else:
                            msg = json.dumps({u'uuid': self.client_uuid, u'error':'Could not find the given intent name'})
                    except:
                        msg = json.dumps({u'uuid': self.client_uuid, u'error':'Could not find the given intent name'})
                        logging.debug('File '+self.skill_json+' does not exist')
                #create the skill if it does not exist, or merge and filter the new list with the actual one
                else: 
                    self.file = base64.b64decode(json_msg['file']) #buffer
                    self.skill_file = self.skill_dir+'/'+self.skill
                    logging.debug("Skill Name received: %s" % self.skill)
                    try:
                        with open(self.skill_json) as f: #load the list of intents
                            skills = json.load(f)
                    except:
                        logging.debug('File '+self.skill_json+' does not exist')
                        skills = {'intents':[]} #Create a list if it's not yet created


                    #create the intent 'error if exist'
                    if self.mode == 'post':
                        if not self.skill in skills['intents']:
                            with open(self.skill_file, 'wb') as f: #save the buffer
                                f.write(self.file)
                            skills['intents'].append(self.skill) #add the entity to the list
                            with open(self.skill_json, 'w') as outfile: #save data.json file
                                json.dump(skills, outfile, sort_keys=True, indent=4)
                            msg = json.dumps({u'uuid': self.client_uuid, u'create':'The intent \''+self.skill+'\' is successfully created'})
                        else:
                            msg = json.dumps({u'uuid': self.client_uuid, u'error':'The intent already exists'})


                    #replace the intent 'error if does not exist'
                    elif self.mode == 'put':
                        if self.skill in skills['intents']:
                            with open(self.skill_file, 'wb') as f: #save the buffer
                                f.write(self.file)
                            msg = json.dumps({u'uuid': self.client_uuid, u'reset':'The intent \''+self.skill+'\' is successfully replaced'})
                        else:
                            msg = json.dumps({u'uuid': self.client_uuid, u'error':'The intent does not exist'})

                self.send(msg)


    def prepare_HCLG(self,lmdir):
        test = True
        if os.path.isdir(TEMP_LM_PATH): #remove the tmp directory if exists
            rmtree(TEMP_LM_PATH)
        os.mkdir(TEMP_LM_PATH) #create the temporary folder
        os.mkdir(TEMP_LM_PATH+'/fst') #create the fst folder
        lm_text=TEMP_LM_PATH+'/text' #LM training file path
        entity_tmp=TEMP_LM_PATH+'/fst' #directory to save the entities
        g2pDir=lmdir+'/g2p/'
        dictDir=lmdir+'/dict/'
        lexicon={} #lexicon
        words={} #words with symbol '-'
        cmds=[] #commands

        #prepare the lexicon
        if os.path.isfile(dictDir+'/lexicon.txt'):
            with open(dictDir+'/lexicon.txt') as f: #load lexicon
                lex = f.readlines()
            for e in lex:
                e = e.strip().split('\t')
                if len(e) > 1:
                    lexicon[e[0]]=e[1]
                else:
                    e = e.strip().split(' ')
                    lexicon[e[0]]=' '.join(e[1:])

        #prepare the words
        if os.path.isfile(dictDir+'/lexicon.txt'):
            with open(dictDir+'/lexicon.txt') as f: #load lexicon
                lex = f.readlines()
            for e in lex:
                if '-' in e:
                    e = e.strip().split('\t')
                    if len(e) == 1:
                        e = e.strip().split(' ')
                    w=e[0].strip()
                    words[re.sub(r'-',' ',w)]=w

        #prepare the set of commands
        try:
            with open(self.skill_json) as f: #load the list of skills
                skills = json.load(f)
        except:
            msg = json.dumps({u'uuid': self.client_uuid, u'error':'No intent has been included.'})
            return False, msg

        for skill in skills['intents']: #load all skills
            self.skill_file = self.skill_dir+'/'+skill
            try:
                with open(self.skill_file, 'r', encoding='utf-8') as f: #load each skill
                    txt = f.readlines()
            except:
                msg = json.dumps({u'uuid': self.client_uuid, u'error':'Intent '+self.skill_file+' file does not exist.'})
                return False, msg
            txt = list(map(lambda s: s.strip(), txt))
            txt = self.transform_skill(skill,txt,words) #Normalize the intent commands
            cmds = list(cmds + txt)
        if len(cmds) == 0:
            msg = json.dumps({u'uuid': self.client_uuid, u'error':'No intent has been found.'})
            return False, msg
        with open(lm_text, 'w', encoding='utf-8') as f: #save the normalized commands into a file
            for i in cmds:
                f.write(i+'\n')

        #prepare the set of entities
        try:
            with open(self.entity_json) as f: #load the list of entities
                entities = json.load(f)
        except:
            entities={'entities':[]}
        with open(entity_tmp+'/.entities', 'w', encoding='utf-8') as f:
            for e in entities['entities']:
                ########## NORMALIZATION
                self.entity_file = self.entity_dir+'/'+e
                try:
                    with open(self.entity_file, 'r', encoding='utf-8') as file: #load each skill
                        vals = file.readlines()
                except:
                    msg = json.dumps({u'uuid': self.client_uuid, u'error':'Entity '+self.entity_file+' file does not exist.'})
                    return False, msg
                vals = list(map(lambda s: s.strip(), vals))
                vals = self.transform_entity(e,vals,lexicon)    #Normalize the entity values
                with open(entity_tmp+'/'+e, 'w', encoding='utf-8') as file: #save the normalized entity into a file
                    for i in vals:
                        file.write(i+'\n')                
                ##########
                #copyfile(self.entity_dir+'/'+e,entity_tmp+'/'+e)
                f.write(e+'\n')
        
        #check entities
        line=' '.join(cmds)
        entities_cmds = list(set(re.findall("#\w*",line))) #get all defined entities in the intents
        entities_cmds = list(map(lambda s: re.sub('#','',s), entities_cmds)) #remove identifier from the returned entities for comparison
        out=[]
        msg=""
        for e in entities_cmds:
            if e not in entities['entities'] or not os.path.isfile(self.entity_dir+'/'+e): #check if the intent entities are already initialized in entities 'data.json'
                out.append(e)
        if len(out)!=0:
            test = False
            msg = json.dumps({u'uuid': self.client_uuid, u'error':'The entities \''+' '.join(out)+'\' that are defined in the intents are not yet initialized.'})
            return test, msg
        
        #check LM files
        out=[]
        for e in [g2pDir+'/.tool', g2pDir+'/model', dictDir+'/lexicon.txt', dictDir+'/lexiconp.txt', dictDir+'/extra_questions.txt', dictDir+'/nonsilence_phones.txt', dictDir+'/optional_silence.txt', dictDir+'/silence_phones.txt']:
            if not os.path.isfile(e): #check if the intent entities are already initialized in entities 'data.json'
                out.append(e)
        if len(out)!=0:
            test = False
            msg = json.dumps({u'uuid': self.client_uuid, u'error':'No such file \''+' '.join(out)+'\'. The language model could not be generated.'})
            return test, msg

        return test, msg


    def transform_entity(self, name, lst, lexicon={}):
        #convert to lowercase
        #remove duplicates
        #replace points and virgule with new lines
        #remove special characters
        #remove duplicate words pronunciation

        newLst = []
        values = list(map(lambda s: s.strip().lower(), lst)) #convert to lowercase
        values = list(set(values)) #remove duplicates from list
        values = list(map(lambda s: s.split(','), values)) #split commands based on comma character
        values = [item for sublist in values for item in sublist] #convert list of list to list (flat list)
        values = list(map(lambda s: s.split('.'), values)) #split commands based on point character
        values = [item for sublist in values for item in sublist] #convert list of list to list (flat list)
        values = list(map(lambda s: s.strip(), values)) #remove the begin-end of line spaces
        values = list(set(list(filter(None, values)))) #remove empty element from list
        for line in values:
            line = re.sub(r"’","'",line) #replace special character
            line = re.sub(r"'","' ",line) #add space after quote symbol
            line = re.sub(r"[^a-z àâäçèéêëîïôùûü_'\-#]","",line) #remove other symbols
            newLst.append(line.strip()) #add the resulting value
        newLst = list(set(list(filter(None, newLst)))) #remove empty element from list
        newLst.sort()

        return newLst

    def transform_skill(self, name, txt, words={}):
        text = []
        txt = list(map(lambda s: s.lower(), txt)) #convert to lowercase
        txt = list(map(lambda s: s.split(','), txt)) #split commands based on comma character
        txt = [item for sublist in txt for item in sublist] #convert list of list to list (flat list)
        txt = list(map(lambda s: s.split('.'), txt)) #split commands based on point character
        txt = [item for sublist in txt for item in sublist] #convert list of list to list (flat list)
        txt = list(map(lambda s: s.strip(), txt)) #remove the begin-end of line spaces
        txt = list(set(list(filter(None, txt)))) #remove empty element from list
        for line in txt:
            line = re.sub(r"^##.*","",line) #remove intent identifier
            line = re.sub(r"^ *- *","",line) #remove starting character
            line = re.sub(r"\)",") ",line) #correct some bugs in the skill file
            line = re.sub(r"\[[^\[]*\]","",line) #remove entity values
            line = re.sub(r"_[^\(]*\)",")",line) #remove underscore from entity name
            line = re.sub(r"\(","#",line) #add entity identifier
            line = re.sub(r"\)","",line) #remove parenthesis
            line = re.sub(r"’","'",line) #replace special character
            line = re.sub(r"'","' ",line) #add space after quote symbol
            line = re.sub(r"  *"," ",line) #remove double space
            line = re.sub(r"æ","ae",line) #replace special character
            line = re.sub(r"œ","oe",line) #replace special character
            line = re.sub(r"[^a-z àâäçèéêëîïôùûü_'\-#]","",line) #remove other symbols
            text.append(line.strip()) #add the resulting command to the set of intent
        text = list(set(list(filter(None, text)))) #remove empty element from list
        text.sort()

        #replace words
        if len(words) > 0:
            text_tmp = ' \n '.join(text) #convert list to str
            text_tmp = ' '+text_tmp+' '
            for w in words.keys():
                if w in text_tmp:
                    text_tmp = re.sub(' '+w+' ',' '+words[w]+' ',text_tmp)
            text = text_tmp.strip().split(' \n ') #re-build list

        #remove sub-commands
        for i in range(0,len(text)):
            for j in range(0,len(text)):
                if i != j and " "+text[i].strip()+" " in " "+text[j]+" ":
                    #logging.debug(text[i]+' => '+text[j])
                    text[i]=""
                    break
        text  = list(set(list(filter(None, text)))) #remove empty elements from list
        logging.debug('skill:'+name+' all='+str(len(txt))+' new='+str(len(text)))
        text.sort()
        return text


    def post(self, m):
        logging.debug('POST received')

    def send_result(self, result=""):
        msg = ""
        logging.debug("Transcription is : %s" % result)
        try:
            data = json.loads(result)
            if 'error' in data.keys():
                msg = json.dumps({u'uuid': self.client_uuid, u'error':data['error']})
            else:
                jsonObj = {u'uuid': self.client_uuid, u'transcription':data['utterance']}
                if INDICE_DATA:
                    jsonObj[u'confidence_score']=data['score']
                msg = json.dumps(jsonObj)
        except Exception as e:
            logging.debug(e)
            msg = json.dumps({u'uuid': self.client_uuid, u'error':'worker Failed to create transcription file! check server log to identify the error.'})
        self.client_uuid = None
        self.send(msg)

    def send_error(self, message):
        msg = json.dumps({u'uuid': self.client_uuid, u'error':message})
        self.send(msg)

    def closed(self, code, reason=None):
        pass

    def finish_request(self):
        pass

@tenacity.retry(
        wait=tenacity.wait.wait_fixed(2),
        stop=tenacity.stop.stop_after_delay(45),
        retry=tenacity.retry_if_exception(ConnexionRefusedException)
    )
def connect_to_server(ws):
    try:
        logging.info("Attempting to connect to server at %s:%s" % (SERVER_IP, SERVER_PORT))
        ws.connect()
        logging.info("Worker succefully connected to server at %s:%s" % (SERVER_IP, SERVER_PORT))
        ws.run_forever()
    except KeyboardInterrupt:
        logging.info("Worker interrupted by user")
        ws.close()
    except Exception as e:
        if "[Errno 113]" in str(e):
            logging.info("Failed to connect")
            raise NoRouteException
        if "[Errno 111]" in str(e):
            logging.info("Failed to connect")
            raise ConnexionRefusedException
        logging.debug(e)
    logging.info("Worker stopped")

def main():
    parser = argparse.ArgumentParser(description='Worker for linstt-dispatch')
    parser.add_argument('-u', '--uri', default="ws://"+SERVER_IP+":"+SERVER_PORT+SERVER_TARGET, dest="uri", help="Server<-->worker websocket URI")

    args = parser.parse_args()
    #thread.start_new_thread(loop.run, ())
    if not os.path.isdir(TEMP_FILE_PATH):
        os.mkdir(TEMP_FILE_PATH)

    logging.basicConfig(level=logging.DEBUG, format="%(levelname)8s %(asctime)s %(message)s ")
    logging.info('Starting up worker')
    ws = WorkerWebSocket(args.uri)
    try:
        connect_to_server(ws)
    except Exception:
        logging.error("Worker did not manage to connect to server at %s:%s" % (SERVER_IP, SERVER_PORT))
if __name__ == '__main__':
    main()
