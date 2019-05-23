FROM debian:9
MAINTAINER Ilyes REBAI <irebai@linagora.com>

# Install all our dependencies and set some required build changes
RUN apt-get update && apt-get install -y \
    autoconf \
    automake \
    unzip \
    bc \
    bzip2 \
    default-jre \
    g++ \
    git \
    gzip \
    libatlas3-base \
    libtool-bin \
    make \
    python2.7 \
    python3   \
    python-dev \
    python3-dev \
    python-pip \
    python3-pip \
    sox \
    libav-tools \
    subversion \
    vorbis-tools \
    wget \
    swig \
    zlib1g-dev &&\
    apt-get clean autoclean && \
    apt-get autoremove -y && \
    ln -s /usr/bin/python2.7 /usr/bin/python ; ln -s -f bash /bin/sh

ENV BASE_DIR /opt/speech-to-text

# Build kaldi
## Install OpenFst
RUN cd /opt && git clone https://github.com/kaldi-asr/kaldi.git && \
    cd /opt/kaldi/tools && make -j$(nproc)

# Install packages
RUN cd /opt/kaldi/tools && \
    extras/install_mkl.sh && \
    extras/install_phonetisaurus.sh && \
    extras/install_irstlm.sh

## Install main functions
RUN cd /opt/kaldi/src && \
    sed -i -e ':a;N;$!ba;s:\\\n::g' Makefile && \
    sed -i -e 's:^SUBDIRS = .*$:SUBDIRS = base matrix util feat tree gmm transform fstext hmm lm decoder lat cudamatrix nnet bin fstbin nnet2 nnet3 rnnlm chain ivector online2 latbin online2bin lmbin:g' -e 's:^MEMTESTDIRS = .*$:MEMTESTDIRS = :g' Makefile && \
    ./configure --shared && make depend -j$(nproc) && make -j$(nproc)

WORKDIR $BASE_DIR

# Install python dependencies
COPY requirements.txt .
RUN pip3 install -r requirements.txt

# Install sequitur
RUN cd /opt && pip3 install numpy && \
 pip3 install git+https://github.com/sequitur-g2p/sequitur-g2p@master && git clone https://github.com/sequitur-g2p/sequitur-g2p

# Set locale to UTF-8
RUN apt-get install -y locales && \
    echo "fr_FR.UTF-8 UTF-8" >> /etc/locale.gen && \
    locale-gen

# Set kaldi path
ENV PATH /opt/kaldi/tools/openfst/bin:/opt/kaldi/src/online2bin:/opt/kaldi/src/fstbin:/opt/kaldi/src/lmbin:/opt/kaldi/src/latbin:/opt/kaldi/src/bin:/opt/kaldi/tools/phonetisaurus-g2p/src/scripts:/opt/kaldi/tools/phonetisaurus-g2p:/opt/sequitur-g2p/g2p.py:/opt/kaldi/tools/irstlm/bin:/opt/kaldi/egs/wsj/s5/utils:$PATH

COPY . .

RUN ln -s /opt/kaldi/egs/wsj/s5/utils $BASE_DIR/scripts && touch $BASE_DIR/scripts/path.sh

# Set the default command
CMD ./worker_offline.py

