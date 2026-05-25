FROM public.ecr.aws/lambda/python:3.12

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt --target "${LAMBDA_TASK_ROOT}"

COPY geometry.py extractor.py server.py "${LAMBDA_TASK_ROOT}/"

CMD ["server.handler"]
