#!/usr/bin/env python3
"""
Script to start the local LLM server with configurable n_ctx and n_gpu_layers.
"""
import argparse
import subprocess
import sys
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description='Start local LLM server')
    parser.add_argument('--n-ctx', type=int, default=50000,
                       help='Context window size (default: 50000)')
    parser.add_argument('--n-gpu-layers', type=int, default=10,
                       help='Number of layers to offload to GPU (default: 10)')
    
    args = parser.parse_args()
    
    # Build the command
    cmd = [
        'llama-server',
        '--port', '8080',
        '--host', 'localhost',
        '--ctx-size', str(args.n_ctx),
        '--n-gpu-layers', str(args.n_gpu_layers)
    ]
    
    print(f"Starting LLM server with n_ctx={args.n_ctx}, n_gpu_layers={args.n_gpu_layers}")
    print(f"Command: {' '.join(cmd)}")
    
    try:
        # Start the server
        process = subprocess.Popen(cmd)
        print("LLM server started successfully.")
        print("Press Ctrl+C to stop the server.")
        
        # Wait for the process to complete (it should run until killed)
        process.wait()
    except FileNotFoundError:
        print("Error: llama-server not found. Please ensure it's installed and in PATH.", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nShutting down server...")
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

if __name__ == '__main__':
    main()