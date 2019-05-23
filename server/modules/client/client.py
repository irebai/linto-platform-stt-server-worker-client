#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Jan  4 11:10:18 2018

@author: rbaraglia
"""

import requests
import json
import logging
import argparse

SERVER_IP = u"localhost"
SERVER_PORT = u"8888"
SERVER_TARGET = u"/client/post/speech"
        
def main():
    parser = argparse.ArgumentParser(description='Client for linstt-dispatch')
    parser.add_argument('-u', '--uri', default="http://"+SERVER_IP+":"+SERVER_PORT+SERVER_TARGET, dest="uri", help="Server adress")
    parser.add_argument('audioFile', help="The .wav file to be transcripted" )

    args = parser.parse_args()
    with open(args.audioFile, 'rb') as f: 
        print("Sendind request to transcribe file %s to server at %s" % (args.audioFile, "http://"+SERVER_IP+":"+SERVER_PORT+SERVER_TARGET))
        r = requests.post(args.uri, files={'wavFile': f})
        print(r.json()['transcript']
        
if __name__ == '__main__':
    main()