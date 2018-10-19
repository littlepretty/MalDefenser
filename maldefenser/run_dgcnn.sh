#!/bin/bash

DATA="${1-SMALLACFG}"
GPU="${2-1}"  # select the GPU number, 0-3

# general/default settings
gm=DGCNN  # model
gpu_or_cpu=gpu
mlp_type=vanilla # rap or vanilla
cache_file=cached_${DATA,,}_graphs.pkl

# dataset-specific settings
case ${DATA} in
MSACFG)
  use_cached_data=False
  ;;
SMALLACFG)
  use_cached_data=False
  ;;
*)
  use_cached_data=False
  ;;
esac

CUDA_VISIBLE_DEVICES=${GPU} python3.7 cross_valid.py \
  -seed 1 \
  -data ${DATA} \
  -gm $gm \
  -mode ${gpu_or_cpu} \
  -mlp_type ${mlp_type} \
  -use_cached_data ${use_cached_data} \
  -cache_file ${cache_file}

echo "Cross validatation history:"
cat ${DATA}Run0.hist
