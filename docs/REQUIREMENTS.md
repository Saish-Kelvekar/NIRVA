# NIRVA — Software Requirements Specification

## 1. Purpose

This document defines the functional and non-functional requirements for NIRVA, an offline-capable, edge-first AI assistant designed to answer Dandeli-specific queries.

The system will use a domain-adapted Small Language Model deployed directly on Android devices.

## 2. Functional Requirements

### FR-01: Local AI Question Answering

- The application shall accept natural-language questions related to Dandeli.
- The application shall generate responses using a locally deployed SLM.
- The model shall support multi-turn conversations within the available context window.
- The application shall display generated responses clearly.

### FR-02: Domain Restriction

- The application shall identify whether an incoming query is relevant to Dandeli.
- The application shall reject unrelated general-purpose queries.
- The application shall provide an appropriate explanation when rejecting a query.
- Domain restriction shall not depend exclusively on the model's system prompt.

### FR-03: Domain-Specific Model Adaptation

- The project shall use a suitable pretrained SLM as its base model.
- The model shall be adapted using instruction-based training data.
- LoRA / PEFT shall be explored for parameter-efficient fine-tuning.
- The project shall support saving and loading trained adapters.
- The adapted model shall be evaluated against the original base model.

### FR-04: Local Knowledge and Information

- The training dataset shall contain verified Dandeli-specific information.
- Information shall cover relevant tourist and resident use cases.
- The dataset shall distinguish factual information from general conversational instructions.
- The application shall avoid presenting unsupported information as verified fact.
- The project shall document the limitations of model-based knowledge retention.

### FR-05: On-Device Model Inference

- The application shall execute SLM inference directly on the Android device.
- Normal AI question answering shall not require a cloud inference API.
- The application shall operate without an active internet connection after the necessary model and application data have been installed.
- The application shall support an appropriate local inference runtime.

### FR-06: Model Optimization

- The project shall investigate quantization to reduce model storage requirements.
- The project shall evaluate suitable GGUF model formats and llama.cpp-based inference.
- The project shall investigate adapter merging and model conversion where required.
- Knowledge distillation may be explored as an advanced optimization technique.

### FR-07: Model Evaluation

The project shall evaluate:

- Local question-answering correctness.
- Domain classification accuracy.
- Out-of-domain rejection accuracy.
- Response consistency.
- Base versus fine-tuned model performance.
- Quantized versus unquantized model performance.

### FR-08: Performance Monitoring

The project shall measure:

- Model loading time.
- Inference latency.
- Generated tokens per second.
- Peak memory consumption where measurable.
- Model storage size.
- Battery consumption and thermal behaviour where measurable.

## 3. Non-Functional Requirements

### NFR-01: Offline Operation

Normal AI inference shall work without an internet connection.

### NFR-02: Resource Efficiency

The initial target shall be Android devices with at least 4 GB RAM.

The model and inference pipeline shall be optimized to operate within the available device resources.

Compatibility shall be established through actual device testing.

### NFR-03: Response Performance

The application shall aim to provide responsive answers on supported Android devices.

Inference latency and throughput shall be benchmarked and documented rather than assumed.

### NFR-04: Reliability

The application shall handle:

- Empty queries.
- Invalid input.
- Model loading failures.
- Insufficient memory.
- Unsupported device configurations.
- Unrelated queries.
- Questions for which the model lacks sufficient knowledge.

### NFR-05: Privacy

Normal AI queries shall be processed locally.

The application shall not require sending user conversations to an external AI inference service.

### NFR-06: Cost

The project shall target zero development expenditure and zero recurring server costs.

Paid AI inference APIs and continuously running cloud inference infrastructure shall not be required.

### NFR-07: Maintainability

The application, model pipeline, training scripts and evaluation components shall be organized into modular components.

### NFR-08: Usability

The application shall provide a simple Android interface suitable for both residents and tourists.

## 4. Technical Constraints

1. The primary deployment platform is Android.
2. The initial minimum device target is 4 GB RAM.
3. The model must support a compatible local inference runtime.
4. The initial optimization direction is 4-bit quantization.
5. Model adaptation shall use LoRA / PEFT where supported.
6. Model training and conversion shall be performed during development, not on the user's phone.
7. The project shall not depend on cloud-hosted AI inference.
8. RAG is excluded from the initial implementation.
9. The project shall use models and datasets whose licences permit the intended use and distribution.

## 5. Acceptance Criteria

| ID | Requirement | Acceptance condition |
|---|---|---|
| AC-01 | Local inference | A question generates a response without an internet connection. |
| AC-02 | Domain adherence | The system answers supported Dandeli-related test questions. |
| AC-03 | Query rejection | Unrelated test questions are appropriately rejected. |
| AC-04 | Model adaptation | Base and LoRA-adapted models can be compared using the same test dataset. |
| AC-05 | Quantization | A quantized model can be loaded and evaluated using the selected runtime. |
| AC-06 | Android compatibility | The application runs on at least one tested Android device with 4 GB RAM. |
| AC-07 | Performance | RAM usage, model loading time and generation speed are recorded. |
| AC-08 | Offline functionality | Core AI functionality remains available after disconnecting from the internet. |
| AC-09 | Privacy | Normal inference does not transmit queries to a cloud AI service. |
| AC-10 | Cost | No paid or continuously running inference server is required. |

## 6. Out of Scope

The following are not part of the initial release:

- Retrieval-Augmented Generation (RAG).
- Cloud-based language-model inference.
- General-purpose AI assistance.
- Voice interaction.
- Real-time online business information.
- Automatic live navigation and transport updates.
- Multi-agent systems.

These may be considered for future versions after evaluating the initial release.

## 7. Project Success

NIRVA will be considered successful when it demonstrates that a domain-adapted Small Language Model can provide useful Dandeli-specific assistance while operating locally on a supported Android device with constrained hardware resources.

The project must demonstrate measurable results in model adaptation, domain adherence, quantization, inference performance and offline operation.