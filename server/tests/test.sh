#!/bin/sh

i=0
while [ "$i" -lt 100 ]
do    
    curl -F "wavFile=@mocanu-Samy.wav" http://localhost:8888/client/post/speech &
    echo $i
    i=`expr $i + 1`
done