FROM python:3.11-slim
WORKDIR /workspace
COPY minemind/evaluation/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY minemind/evaluation /workspace/evaluation
CMD ["python", "evaluation/run_benchmark.py"]
