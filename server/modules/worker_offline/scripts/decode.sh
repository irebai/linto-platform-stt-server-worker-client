#!/bin/bash

# Copyright 2018 Linagora (author: Ilyes Rebai)
# LinSTT project


# Begin configuration section.
tmpdir=tmpfolder
cmd=run.pl
online_conf=systems/online.conf
decoder=dnn3
nj=1
# End configuration section.

. parse_options.sh || exit 1;

if [ $# != 9 ]; then
   echo "Usage: $0 [options] <amodel-dir> <lmodel-dir> <wav-file> <min_active> <max_active> <beam> <lattice_beam> <acwt> <fsf>";
   exit 1;
fi
amdir=$1
lmdir=$2
wavFile=$3
min_active=$4
max_active=$5
beam=$6
lattice_beam=$7
acwt=$8
fsf=$9

function confidence_score {
  #confidence_score $log "$text" $fileRootName
  confidence=$tmpdir/confidence_score.log
  decode=$1
  text=$2
  file=$3
  $cmd JOB=1:1 $confidence \
    lattice-to-ctm-conf2 --acoustic-scale=$acwt  \
     ark:$tmpdir/decode.lat \
     $tmpdir/sentence_confidence_score.txt
  #Bayes_Risk
  br=$(cat $confidence | grep "For utterance $file," | cut -d ',' -f2 | cut -d ' ' -f4) #avg_confidence_per_word
  #AVG_Confidence_per_Word
  cw=$(cat $confidence | grep "For utterance $file," | cut -d ',' -f3 | cut -d ' ' -f5)
  if [ $cw == "-nan" ]; then
    cw=0
  fi
  #STD_per_sentence
  std=$(cat $confidence | grep "For utterance $file," | cut -d ',' -f4 | cut -d ' ' -f5)
  if [ $std == "-nan" ]; then
    std=0
  fi
  #score=data['cw']*(1-data['std'])

  #Transcription
  #text=$(cat $decode | sed -e "s: *$::g" -e "s:^ *::g")
  echo -n "{\"utterance\":\"$text\",\"score\":$score}" > $decode
}

fileRootName=$(basename $wavFile)
log=$tmpdir/decode.log
decode_conf=$online_conf
decode_mdl=$amdir/final.mdl
decode_graph=$lmdir/HCLG.fst
decode_words=$lmdir/words.txt

if [ $decoder == "dnn" -o $decoder == "dnn2" ]; then

  test=true
  $cmd JOB=1:1 $log \
  online2-wav-nnet2-latgen-faster --do-endpointing=false \
     --online=false \
     --config=$decode_conf \
     --max-active=$max_active --beam=$beam --lattice-beam=$lattice_beam \
     --acoustic-scale=$acwt \
     --word-symbol-table=$decode_words \
      $decode_mdl \
      $decode_graph \
      "ark:echo $fileRootName $fileRootName|" "scp:echo $fileRootName $wavFile|" \
      ark:$tmpdir/decode.lat

elif [ $decoder == "dnn3" ]; then

  test=true
  $cmd JOB=1:1 $log \
  online2-wav-nnet3-latgen-faster --do-endpointing=false \
    --frames-per-chunk=20 \
    --online=false \
    --frame-subsampling-factor=$fsf \
    --config=$decode_conf \
    --minimize=false --min-active=$min_active --max-active=$max_active --beam=$beam --lattice-beam=$lattice_beam \
     --acoustic-scale=$acwt \
     --word-symbol-table=$decode_words \
      $decode_mdl \
      $decode_graph \
      "ark:echo $fileRootName $fileRootName|" "scp:echo $fileRootName $wavFile|" \
      ark:$tmpdir/decode.lat

else
    test=false
    echo -n "{\"error\":\"Unsupported decoder\"}" > $log
fi

if $test; then
  error=$(cat $log | grep "^ERROR " | head -n 1 | sed "s/WaveData: expected RIFF or RIFX, got .*/WaveData: expected RIFF or RIFX/g")
  if [[ $error == "" ]]; then
    text=$(cat $log | grep "^$fileRootName" | cut -d ' ' -f2- | sed -e "s: *$::g" -e "s:^ *::g" | sed 's/#nonterm:[^ ]* //g')
    echo -n "{\"utterance\":\"$text\",\"score\":1}" > $log
  else
    echo -n "{\"error\":\"$error\"}" > $log
  fi
fi
