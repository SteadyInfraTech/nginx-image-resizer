FROM python:3.13-alpine
WORKDIR /workspace
COPY tests /workspace/tests
CMD ["python", "-m", "unittest", "discover", "-s", "tests", "-v"]
