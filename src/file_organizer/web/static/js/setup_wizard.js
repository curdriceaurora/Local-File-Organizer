(() => {
  let currentStep = 1;
  let selectedMode = null;
  let detectionData = null;

  const showStep = (stepNumber) => {
    document.querySelectorAll(".wizard-step").forEach((step) => {
      step.classList.remove("wizard-step-active");
      if (parseInt(step.dataset.step) === stepNumber) {
        step.classList.add("wizard-step-active");
      }
    });

    document.querySelectorAll(".progress-step").forEach((step) => {
      const stepNum = parseInt(step.dataset.step);
      step.classList.remove("progress-step-active", "progress-step-completed");
      if (stepNum === stepNumber) {
        step.classList.add("progress-step-active");
      } else if (stepNum < stepNumber) {
        step.classList.add("progress-step-completed");
      }
    });

    currentStep = stepNumber;
  };

  const updateDetectionStatus = (elementId, status, message) => {
    const element = document.getElementById(elementId);
    if (!element) return;

    if (status === "checking") {
      element.innerHTML = '<span class="status-checking">Checking...</span>';
    } else if (status === "success") {
      element.innerHTML = `<span class="status-success">✓ ${message}</span>`;
    } else if (status === "warning") {
      element.innerHTML = `<span class="status-warning">⚠ ${message}</span>`;
    } else if (status === "error") {
      element.innerHTML = `<span class="status-error">✗ ${message}</span>`;
    }
  };

  const detectCapabilities = async () => {
    updateDetectionStatus("ollama-status", "checking", "Checking...");
    updateDetectionStatus("memory-status", "checking", "Checking...");
    updateDetectionStatus("gpu-status", "checking", "Checking...");
    updateDetectionStatus("models-status", "checking", "Checking...");

    try {
      const response = await fetch("/api/v1/setup/capabilities", {
        method: "GET",
        headers: {
          "Content-Type": "application/json",
        },
      });

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }

      detectionData = await response.json();

      if (detectionData.ollama.installed && detectionData.ollama.running) {
        updateDetectionStatus(
          "ollama-status",
          "success",
          `Installed (${detectionData.ollama.version || "unknown version"})`
        );
      } else if (detectionData.ollama.installed) {
        updateDetectionStatus("ollama-status", "warning", "Installed but not running");
      } else {
        updateDetectionStatus("ollama-status", "error", "Not installed");
      }

      updateDetectionStatus(
        "memory-status",
        "success",
        `${detectionData.hardware.total_ram_gb.toFixed(1)} GB available`
      );

      if (detectionData.hardware.gpu_available) {
        const gpuInfo = detectionData.hardware.gpu_name
          ? `${detectionData.hardware.gpu_name}`
          : "Available";
        const vramInfo = detectionData.hardware.gpu_vram_gb
          ? ` (${detectionData.hardware.gpu_vram_gb.toFixed(1)} GB)`
          : "";
        updateDetectionStatus("gpu-status", "success", `${gpuInfo}${vramInfo}`);
      } else {
        updateDetectionStatus("gpu-status", "warning", "No GPU detected");
      }

      if (detectionData.models && detectionData.models.length > 0) {
        updateDetectionStatus(
          "models-status",
          "success",
          `${detectionData.models.length} model(s) available`
        );
      } else {
        updateDetectionStatus("models-status", "warning", "No models installed");
      }

      const recommendationPanel = document.getElementById("recommendation-panel");
      const recommendationText = document.getElementById("recommendation-text");
      if (recommendationPanel && recommendationText) {
        recommendationPanel.style.display = "block";
        recommendationText.textContent = `Based on your ${detectionData.hardware.total_ram_gb.toFixed(0)} GB RAM and ${
          detectionData.hardware.gpu_available ? "GPU" : "CPU"
        }, we recommend: ${detectionData.hardware.recommended_model}`;
      }

      populateModelDropdowns();

      const btnNext = document.getElementById("btn-next-step2");
      if (btnNext) {
        btnNext.disabled = false;
      }
    } catch (error) {
      updateDetectionStatus("ollama-status", "error", "Detection failed");
      updateDetectionStatus("memory-status", "error", "Detection failed");
      updateDetectionStatus("gpu-status", "error", "Detection failed");
      updateDetectionStatus("models-status", "error", "Detection failed");
    }
  };

  const populateModelDropdowns = () => {
    if (!detectionData || !detectionData.models) return;

    const textModelSelect = document.getElementById("text-model");
    const visionModelSelect = document.getElementById("vision-model");

    if (textModelSelect) {
      textModelSelect.innerHTML = '<option value="">Select a model...</option>';
      detectionData.models.forEach((model) => {
        const option = document.createElement("option");
        option.value = model.name;
        option.textContent = model.name;
        textModelSelect.appendChild(option);
      });

      if (detectionData.hardware.recommended_model) {
        const recommendedOption = Array.from(textModelSelect.options).find((opt) =>
          opt.value.includes(detectionData.hardware.recommended_model)
        );
        if (recommendedOption) {
          textModelSelect.value = recommendedOption.value;
        } else if (detectionData.models.length > 0) {
          textModelSelect.value = detectionData.models[0].name;
        }
      }
    }

    if (visionModelSelect) {
      visionModelSelect.innerHTML = '<option value="">Select a model...</option>';
      const visionModels = detectionData.models.filter(
        (model) => model.name.includes("vision") || model.name.includes("llava")
      );
      visionModels.forEach((model) => {
        const option = document.createElement("option");
        option.value = model.name;
        option.textContent = model.name;
        visionModelSelect.appendChild(option);
      });

      if (visionModels.length > 0) {
        visionModelSelect.value = visionModels[0].name;
      }
    }
  };

  const completeSetup = async () => {
    const form = document.getElementById("setup-form");
    if (!form) return;

    const textModel = document.getElementById("text-model")?.value;
    const visionModel = document.getElementById("vision-model")?.value;
    const methodology = document.getElementById("methodology")?.value;
    const inputDir = document.getElementById("input-dir")?.value;
    const outputDir = document.getElementById("output-dir")?.value;

    if (!textModel) {
      alert("Please select a text model");
      return;
    }

    const customSettings = {
      models: {
        text_model: textModel,
      },
      methodology: methodology || "content_based",
    };

    if (visionModel) {
      customSettings.models.vision_model = visionModel;
    }

    if (inputDir) {
      customSettings.paths = customSettings.paths || {};
      customSettings.paths.input_directory = inputDir;
    }

    if (outputDir) {
      customSettings.paths = customSettings.paths || {};
      customSettings.paths.output_directory = outputDir;
    }

    const btnComplete = document.getElementById("btn-complete");
    if (btnComplete) {
      btnComplete.disabled = true;
      btnComplete.textContent = "Completing Setup...";
    }

    try {
      const response = await fetch("/api/v1/setup/complete", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          mode: selectedMode || "quick_start",
          profile: "default",
          custom_settings: customSettings,
        }),
      });

      if (!response.ok) {
        throw new Error(`Setup failed: ${response.status}`);
      }

      const result = await response.json();

      if (result.success) {
        showStep(4);
      } else {
        alert(`Setup failed: ${result.errors.join(", ")}`);
        if (btnComplete) {
          btnComplete.disabled = false;
          btnComplete.textContent = "Complete Setup";
        }
      }
    } catch (error) {
      alert(`Setup error: ${error.message}`);
      if (btnComplete) {
        btnComplete.disabled = false;
        btnComplete.textContent = "Complete Setup";
      }
    }
  };

  document.body.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;

    if (target.matches(".mode-select")) {
      selectedMode = target.dataset.mode;
      showStep(2);
      setTimeout(() => {
        void detectCapabilities();
      }, 300);
      return;
    }

    if (target.matches("#btn-back-step2")) {
      showStep(1);
      return;
    }

    if (target.matches("#btn-next-step2")) {
      showStep(3);
      return;
    }

    if (target.matches("#btn-back-step3")) {
      showStep(2);
      return;
    }

    if (target.matches("#btn-complete")) {
      void completeSetup();
      return;
    }
  });
})();
