FROM python:3.13-alpine
WORKDIR /workspace
COPY tests /workspace/tests
COPY tools /workspace/tools
CMD ["python", "-m", "unittest", "discover", "-s", "tests", "-v"]
COPY validator /workspace/validator
