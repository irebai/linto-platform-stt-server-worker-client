#!/bin/bash

# Copyright 2018 Linagora (author: Ilyes Rebai; email: irebai@linagora.com)
# LinSTT project

# Param
order=2
. parse_options.sh || exit 1;
# End

# Begin configuration section.
model=$1 # the path of the acoustic model
lmodel=$2 # the path to the decoding graph
lmgen=$3 # the path to the language generation directory
out=$4 # the output folder where to save the generated files


## Working param
dict=$lmgen/dict
g2p_model=$lmgen/g2p/model
g2p_tool=$(cat $lmgen/g2p/.tool)

## Create Output folders
lex=$out/lexicon
lang=$out/lang
graph=$out/graph
fst=$out/fst
arpa=$out/arpa
log=$out/update.log

mkdir -p $out $lex $fst
touch $log
# End configuration section.

################################################## CHECK THE OOV WORDS ########################################
#extract uniq words
cat $fst/* $out/text | tr " " "\n" | sed 's:^#.*$::g' | sed '/^\s*$/d' | sort | uniq | \
 tr "[[:upper:]]" "[[:lower:]]" > $lex/full_vocab
#extract oov words
awk 'NR==FNR{words[$1]; next;} !($1 in words)' $dict/lexicon.txt $lex/full_vocab | sort | uniq | egrep -v '<.?s>' > $lex/oov_vocab
###############################################################################################################

################################################## UPDATE THE DICTIONARY ######################################
#update dictionary (if there are oov words)
cp -r $dict $out/dict
if [ -s $lex/oov_vocab ]; then
  #extract pronunciations for oov words
  [ $g2p_tool == "phonetisaurus" ] && phonetisaurus-apply --model $g2p_model --word_list $lex/oov_vocab > $lex/lexicon.txt
  [ $g2p_tool == "sequitur" ]      && g2p.py --encoding=utf-8 --model=$g2p_model --apply $lex/oov_vocab > $lex/lexicon.txt

  #check if all oov have pronunciations
  nb_oov=$(wc -l < $lex/oov_vocab)
  nb_lex=$(wc -l < $lex/lexicon.txt)
  if [ $nb_oov -ne $nb_lex ]; then
     echo "{\"error\":\"Error occured during generating pronunciations for new $ett. Some words have empty pronunciations.\"}" > $log
     exit 1
  fi
  #create lexiconp
  cat $lex/lexicon.txt | awk '{a="";for(i=2;i<=NF;i++){a=a""$i" ";} print $1"\t1.0\t"a;}' > $lex/lexiconp.txt
  #update dictionary
  cat $dict/lexicon.txt $lex/lexicon.txt > $out/dict/lexicon.txt
  cat $dict/lexiconp.txt $lex/lexiconp.txt > $out/dict/lexiconp.txt
  if [ -f $dict/lexiconp_silprob.txt ]; then
    rm $out/dict/lexiconp_silprob.txt
    dict_dir_add_pronprobs.sh \
       $out/dict \
       $dict/pronprobs/pron_counts_nowb.txt \
       $dict/pronprobs/sil_counts_nowb.txt \
       $dict/pronprobs/pron_bigram_counts_nowb.txt \
       $out/dict_prons
    rm -r $out/dict
    mv $out/dict_prons $out/dict
  fi
fi
###############################################################################################################

################################################## GENERATE THE LANG DIR ######################################
#create lang dir
prepare_lang.sh $out/dict "<unk>" $lang/tmp $lang
###############################################################################################################

################################################## GENERATE WORD.TXT FILE #####################################
if [ -f $lang/words.txt ]; then
  cp $lang/words.txt $out/words.txt
  c=$(wc -l < $out/words.txt)
  for e in $(cat $fst/.entities); do
    echo "#"$e" "$c >> $out/words.txt
    c=$((c+1))
  done
else
  echo "{\"error\":\"Error occured during updating the lang dir.\"}" > $log
  exit 1
fi
###############################################################################################################

################################################## GENERATE THE ARPA FILE #####################################
#create arpa using irstlm
add-start-end.sh < $out/text > $out/text.s
ngt -i=$out/text.s -n=$order -o=$out/irstlm.${order}.ngt -b=yes 2>/dev/null
tlm -tr=$out/irstlm.${order}.ngt -n=$order -lm=wb -o=$arpa 2>/dev/null

gzip $arpa
###############################################################################################################

################################################## GENERATE THE GRAMMAR FILE ##################################
#create G
cmd=""
for e in $(cat $fst/.entities); do
  awk -f fst.awk $out/words.txt $fst/$e > $fst/$e.int
  fstcompile $fst/$e.int $fst/$e.fst
  cmd1=""
  for e1 in $(cat $fst/$e | tr " " "\n" | grep "#" | sort | uniq); do
    name=$(echo $e1 | sed "s:#::g")
    id=$(grep "$e1 " < $out/words.txt | cut -d' ' -f2)
    cmd1="$cmd1 $fst/$name.fst $id"
  done
  id=$(grep "#$e " < $out/words.txt | cut -d' ' -f2)
  if [ ! -z "$cmd1" ]; then
    fstreplace --epsilon_on_replace $fst/$e.fst -1 $cmd1 | fstarcsort --sort_type=ilabel > $fst/$e.new.fst
    cmd="$cmd $fst/$e.new.fst $id"
  else
    cmd="$cmd $fst/$e.fst $id"
  fi
done
gunzip -c $arpa | arpa2fst --disambig-symbol=#0 --read-symbol-table=$out/words.txt - $fst/G.fst
fstreplace --epsilon_on_replace $fst/G.fst -1 $cmd | fstarcsort --sort_type=ilabel > $lang/G.fst
###############################################################################################################

################################################## GENERATE THE HCLG FILE #####################################
#create HCLG
mkgraph.sh $lang $model $graph
if [ ! -f $graph/HCLG.fst ]; then
  echo "{\"error\":\"Error occured during generating the new graph.\"}" > $log
  exit 1
fi
###############################################################################################################

################################################## SAVE THE GENERATED FILES ###################################
#copy new HCLG to model dir
cp $graph/HCLG.fst $lmodel
cp $graph/words.txt $lmodel
#copy the new dictionary into the model dir
cp $out/dict/lexicon* $dict
#return the oov if exists
if [ -s $lex/oov_vocab ]; then
  oov=$(cat $lex/oov_vocab | tr '\n' ',')
fi
echo "{\"update\":\"Update is done successfully\",\"oov\":\"$oov\"}" > $log
###############################################################################################################


