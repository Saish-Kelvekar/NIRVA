# NIRVA — Project Overview

**Tagline:** Local Intelligence. Built on the Edge.

## 1. Introduction

NIRVA is an offline-capable, edge-first AI application designed to provide location-specific information about Dandeli, Karnataka.

The application aims to serve both local residents and tourists through a Small Language Model (SLM) adapted to understand and respond to Dandeli-related queries.

Unlike conventional AI applications that depend on cloud-hosted language models, NIRVA aims to perform AI inference directly on the user's Android device.

The primary objective is to develop, adapt, optimize and deploy a domain-specific SLM that can operate efficiently on resource-constrained mobile devices.

## 2. Problem Statement

Residents and visitors often need information about local facilities, tourist attractions, transportation, public services and other location-specific resources.

General-purpose AI assistants may provide unrelated information, produce inaccurate local answers or depend on internet connectivity and remote inference services.

There is an opportunity to develop a dedicated local intelligence application that:

- Focuses exclusively on Dandeli-related queries.
- Provides useful information to residents and tourists.
- Operates without depending on a cloud-based AI inference service.
- Remains accessible on Android devices with limited hardware resources.
- Minimizes infrastructure and operational costs.

## 3. Proposed Solution

NIRVA will use a pretrained Small Language Model adapted for the Dandeli domain.

The model will undergo parameter-efficient fine-tuning using LoRA (Low-Rank Adaptation) to improve its ability to follow local-assistant instructions and handle domain-specific queries.

The adapted model will be optimized through quantization and deployed directly on Android devices using a compatible local inference runtime.

The application will also incorporate domain-detection mechanisms to identify unrelated queries and respond appropriately.

## 4. Target Users

### 4.1 Tourists and Visitors

NIRVA will help visitors discover local information, including:

- Tourist attractions and activities.
- Places of interest.
- Local facilities.
- Transportation-related information.
- Travel-related guidance.

### 4.2 Local Residents

NIRVA will help residents access information about:

- Local facilities and services.
- Healthcare and public-service information.
- Government offices and relevant resources.
- Local transportation.
- Other useful town-specific information.

## 5. Project Objectives

1. Develop a domain-adapted Small Language Model for Dandeli-related queries.
2. Explore parameter-efficient fine-tuning using LoRA and PEFT.
3. Implement domain detection and out-of-domain query rejection.
4. Optimize model storage and inference requirements using quantization.
5. Deploy the model directly on Android devices.
6. Target devices with a minimum of 4 GB RAM, subject to compatibility testing.
7. Support normal AI interactions without requiring internet connectivity.
8. Evaluate response quality, domain adherence, memory consumption and inference speed.
9. Minimize development and operational expenses, targeting zero recurring server costs.

## 6. Technical Approach

The project will explore the following technologies and concepts:

- Small Language Models and Transformer architecture.
- Pretrained language model inference.
- Instruction dataset preparation.
- LoRA and Hugging Face PEFT.
- Domain classification and out-of-domain detection.
- Model quantization.
- Knowledge distillation as an advanced optimization technique.
- GGUF model formats and llama.cpp-based inference.
- Android native integration with React Native.
- On-device performance evaluation and benchmarking.

## 7. Project Scope

### 7.1 Included in Initial Scope

- Android application.
- Dandeli-specific AI assistant.
- Pretrained SLM selection and evaluation.
- LoRA-based model adaptation.
- Domain restriction and query rejection.
- Quantized model deployment.
- Local inference without a cloud AI service.
- Offline-capable operation.
- Model performance evaluation.

### 7.2 Excluded from Initial Scope

- Retrieval-Augmented Generation (RAG).
- Cloud-hosted AI inference.
- Paid AI APIs.
- Training a large language model from scratch.
- General-purpose conversational assistance.
- Voice-based interactions.
- Agentic workflows.

These features may be reconsidered in future versions if justified by actual requirements.

## 8. Hardware and Deployment Constraints

The initial deployment target is Android devices with at least 4 GB RAM.

The selected model must be evaluated for:

- Model file size.
- Runtime memory consumption.
- Model loading time.
- Tokens generated per second.
- Response quality.
- Battery consumption and thermal behaviour.

A 4 GB RAM target is an engineering objective, not a guarantee that every device with this specification will support the selected model.

## 9. Cost Constraints

NIRVA aims to be developed and distributed without paid AI inference services or continuously running cloud infrastructure.

The project will prioritize:

- Open-source development tools.
- Locally executed model inference.
- Free development and distribution options.
- Local data storage.
- Optional internet-based application and knowledge updates.

The project targets zero recurring server costs and zero development expenditure.

## 10. Success Criteria

NIRVA will be considered successful when it demonstrates:

1. The ability to answer a defined set of Dandeli-related questions.
2. Appropriate rejection of unrelated questions.
3. Measurable improvements or behavioural changes through fine-tuning.
4. Successful quantized model deployment on supported Android devices.
5. Normal AI inference without an internet connection.
6. Acceptable response quality and inference performance within the target device's resource constraints.
7. No dependency on a paid AI inference server.

## 11. Project Vision

NIRVA aims to demonstrate how Small Language Models can be adapted and optimized to solve a geographically focused real-world information problem.

The project combines domain-specific model adaptation, edge AI, model compression and mobile application development into a practical, locally accessible AI solution.