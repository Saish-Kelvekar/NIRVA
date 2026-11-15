# NIRVA — System Architecture

## 1. Architectural Overview

NIRVA follows an edge-first architecture in which the Small Language Model (SLM) performs inference directly on the user's Android device.

The system separates model development and optimization from mobile application execution.

There are two primary environments:

1. Development and model preparation environment.
2. Android runtime environment.

The development environment handles dataset preparation, fine-tuning, evaluation, model conversion and optimization.

The Android application handles user interaction, domain detection and local model inference.

No continuously running cloud inference server is required.

## 2. High-Level Architecture

### 2.1 Development Environment

The development environment is responsible for preparing the model that will eventually run on Android.

Components:

- Python
- PyTorch
- Hugging Face Transformers
- Hugging Face PEFT
- Training and evaluation scripts
- Model conversion and quantization tools

Workflow:

Pretrained SLM → Dataset preparation → LoRA fine-tuning → Model evaluation → Adapter merging → Quantization → Mobile model artifact.

### 2.2 Android Runtime Environment

The Android application is responsible for interacting with users and executing the optimized model locally.

Components:

- React Native
- TypeScript
- Android native integration
- Local inference runtime
- Local model storage
- Local application data storage

The application sends user prompts to the local inference runtime and displays the generated responses.

## 3. Model Development Pipeline

### 3.1 Base Model Selection

Select a pretrained SLM based on:

- Parameter count.
- Model architecture.
- Model licence.
- Inference compatibility.
- Fine-tuning compatibility.
- Quantization support.
- Memory requirements.

The final model must be selected through benchmarking rather than assuming that a particular model will work on all target devices.

### 3.2 Dataset Preparation

Prepare a domain-specific instruction dataset covering Dandeli.

Potential categories:

- Tourism and attractions.
- Local facilities.
- Healthcare and public services.
- Transportation.
- Local information and frequently asked questions.

Dataset preparation includes:

1. Information collection.
2. Source verification.
3. Data cleaning.
4. Instruction-response formatting.
5. Training and validation splitting.
6. Dataset quality checks.

The dataset should distinguish stable local knowledge from information that may become outdated.

### 3.3 Fine-Tuning

Use LoRA through Hugging Face PEFT to adapt the selected pretrained model.

The process includes:

1. Loading the pretrained model.
2. Preparing tokenized training examples.
3. Configuring LoRA parameters.
4. Applying adapters to selected model modules.
5. Training with an appropriate objective.
6. Monitoring training and validation loss.
7. Saving the trained adapter.

### 3.4 Model Evaluation

Evaluate the original and adapted models using the same test dataset.

Evaluate:

- Local question-answering correctness.
- Domain adherence.
- Out-of-domain rejection.
- Response consistency.
- Training and validation loss.
- Inference performance.

Fine-tuning should only be considered beneficial when evaluation demonstrates measurable improvements in the intended behaviour.

### 3.5 Model Optimization

Prepare the selected model for resource-constrained Android deployment.

Potential operations:

1. Merge LoRA adapters into the base model where appropriate.
2. Convert the model into a supported deployment format.
3. Apply 4-bit quantization.
4. Verify model integrity and output quality.
5. Measure model storage requirements.
6. Benchmark inference performance.

GGUF and llama.cpp are initial candidates for the mobile inference pipeline, subject to architecture and compatibility testing.

Knowledge distillation may be explored if the selected model cannot meet the target device requirements.

## 4. Android Application Architecture

The Android application will use React Native and TypeScript for its user interface.

The application will contain the following logical components.

### 4.1 Presentation Layer

Responsible for:

- Chat interface.
- User input.
- Conversation display.
- Loading and error states.
- Model status.
- Application settings.

### 4.2 Application Logic Layer

Responsible for:

- Input validation.
- Query processing.
- Domain detection.
- Conversation management.
- Response handling.
- Model lifecycle management.

### 4.3 Local Inference Layer

Responsible for:

- Loading the quantized model.
- Tokenizing input.
- Running model inference.
- Generating output tokens.
- Managing inference resources.
- Releasing model resources when appropriate.

The inference layer will communicate with the React Native application through a native Android integration or another compatible local runtime interface.

### 4.4 Local Storage Layer

Responsible for storing:

- Model files.
- Application preferences.
- Conversation history, if enabled.
- Local application metadata.

The initial implementation may use SQLite for structured application data.

## 5. Query Processing Workflow

When a user submits a question, the application follows this process:

1. Receive the user query.
2. Validate the input.
3. Perform domain relevance detection.
4. Reject clearly unrelated queries.
5. Construct the model prompt with appropriate instructions.
6. Pass the prompt to the local inference runtime.
7. Generate the response.
8. Apply response handling and display the result.
9. Handle generation errors or insufficient-resource conditions.

Domain restriction must use explicit application-level logic rather than relying only on a system prompt.

The domain detector may initially use a lightweight classification mechanism. Its implementation will be selected based on evaluation and device-resource constraints.

## 6. Runtime Architecture

The normal inference workflow must not require internet connectivity.

Runtime dependencies:

- Installed Android application.
- Compatible quantized model.
- Local inference runtime.
- Local application data.

Internet connectivity may optionally be used for:

- Initial model downloads.
- Application updates.
- Model updates.
- Local information package updates.

The absence of internet connectivity must not prevent normal inference after installation and model initialization.

## 7. Model and Application Data Flow

### Model preparation flow

Pretrained model → Fine-tuning → Evaluation → Adapter merging → Quantization → Deployment artifact.

### User interaction flow

User → React Native interface → Query validation → Domain detection → Local inference runtime → Generated response → User.

### Update flow

Updated model or application data package → Download when connected → Local validation → Local installation.

Updates must not require a continuously running inference server.

## 8. Deployment Architecture

The primary deployment target is Android.

Initial hardware target:

- Minimum target RAM: 4 GB.
- CPU-based inference as the baseline.
- 4-bit quantized model as the initial optimization target.
- Local model storage.
- Offline inference.

Actual model compatibility and performance must be validated on physical devices.

Hardware acceleration may be investigated where supported, but the initial design should not depend on a particular GPU or neural processing unit.

## 9. Technology Stack

| Layer | Technology |
|---|---|
| Mobile application | React Native |
| Application language | TypeScript |
| Android integration | Kotlin / native integration where required |
| Model development | Python |
| Deep learning | PyTorch |
| Pretrained models | Hugging Face Transformers |
| Fine-tuning | Hugging Face PEFT |
| Model optimization | Quantization and model conversion tools |
| Model format | GGUF candidate |
| Inference runtime | llama.cpp candidate |
| Local structured storage | SQLite |
| Version control | Git and GitHub |

Final runtime and model choices will be confirmed through compatibility experiments.

## 10. Architectural Constraints

1. No cloud-hosted AI inference.
2. No paid AI inference APIs.
3. No mandatory backend server for normal application operation.
4. No RAG in the initial implementation.
5. Model training and optimization happen during development.
6. Normal inference happens locally on Android.
7. The model must be evaluated against the 4 GB RAM target.
8. Model licences must permit the intended use and distribution.

## 11. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Model exceeds available RAM | Test smaller models and quantized formats |
| Slow CPU inference | Optimize context length and generation settings |
| Poor local factual accuracy | Improve verified training data and evaluate model limitations |
| Unrelated queries receive answers | Implement application-level domain detection |
| Quantization reduces quality | Compare quantized and unquantized outputs |
| Mobile runtime incompatibility | Conduct an early Android inference proof of concept |
| Model loading failures | Implement resource checks and error handling |
| Outdated local information | Establish a verified dataset update process |

## 12. Architectural Success Criteria

The architecture will be considered successfully implemented when:

1. A selected SLM can be adapted using LoRA.
2. The adapted model can be converted into a supported mobile deployment format.
3. The quantized model can be loaded on Android.
4. The application can perform inference without an external AI service.
5. Domain-specific queries receive appropriate responses.
6. Unrelated queries are appropriately rejected.
7. Performance is measured on physical devices.
8. The system demonstrates offline operation on supported devices.