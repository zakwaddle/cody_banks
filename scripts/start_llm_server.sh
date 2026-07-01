python3 -m llama_cpp.server \
  --model /storage/gguf/Qwen3-Coder-30B-A3B-Instruct-Q4_K_M.gguf \
  --host 127.0.0.1 \
  --port 8080 \
  --n_ctx 100000 \
  --n_gpu_layers 5 \
  --n_threads 40