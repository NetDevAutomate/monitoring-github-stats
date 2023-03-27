FROM public.ecr.aws/lambda/python:3.8

# Install the function's dependencies using file requirements.txt
COPY requirements.txt  .
RUN pip3 install pip --upgrade
RUN pip3 install -r requirements.txt --target "${LAMBDA_TASK_ROOT}"

# Copy function code
COPY lambda.py ${LAMBDA_TASK_ROOT}

ARG GITHUB_TOKEN
ARG GITHUB_ORG_NAME
ARG GITHUB_TEAM_NAME

ENV GITHUB_TOKEN _GITHUB_TOKEN
ENV GITHUB_ORG_NAME _GITHUB_ORG_NAME
ENV GITHUB_TEAM_NAME _GITHUB_TEAM_NAME

#COPY lambda.py ./

# Set the CMD to your handler (could also be done as a parameter override outside of the Dockerfile)
CMD [ "lambda.lambda_handler" ]