"""End-to-end integration test for LLM tag generation through OrganizationService / FileOrganizer (#1760)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from file_organizer.core.display import show_summary
from file_organizer.core.organization_service import OrganizationService
from file_organizer.core.organize_options import OrganizeOptions, OrganizeRequest
from file_organizer.core.organizer import FileOrganizer
from file_organizer.models.base import ModelConfig, ModelType
from file_organizer.models.vision_schema import TaggedVisionSchema
from file_organizer.services.text_processor import TextAnalysisSchema

pytestmark = [pytest.mark.integration, pytest.mark.ci]


@pytest.fixture
def test_environment(tmp_path: Path) -> tuple[Path, Path]:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create a text file
    (input_dir / "notes.txt").write_text(
        "Team meeting notes for weekly sprint planning.", encoding="utf-8"
    )

    # Create an image file
    img = Image.new("RGB", (50, 50), color="green")
    img.save(input_dir / "landscape.jpg", format="JPEG")

    return input_dir, output_dir


def test_organize_tagging_e2e_populates_operation_tags(test_environment: tuple[Path, Path]) -> None:
    input_dir, output_dir = test_environment

    fake_text_model = MagicMock()
    fake_text_model.config.model_type = ModelType.TEXT
    fake_text_model.is_initialized = True
    fake_text_model.generate_structured.return_value = TextAnalysisSchema(
        description="Team sprint notes.",
        tags=["sprint", "planning", "weekly-notes"],
    )
    fake_text_model.generate.return_value = "notes"

    fake_vision_model = MagicMock()
    fake_vision_model.config.model_type = ModelType.VISION
    fake_vision_model.is_initialized = True
    fake_vision_model.generate_structured.return_value = TaggedVisionSchema(
        description="Green landscape view",
        folder_name="nature",
        filename="green_landscape",
        has_text=False,
        tags=["landscape", "green", "outdoor"],
    )

    with (
        patch(
            "file_organizer.services.text_processor.get_text_model", return_value=fake_text_model
        ),
        patch(
            "file_organizer.services.vision_processor.get_vision_model",
            return_value=fake_vision_model,
        ),
    ):
        service = OrganizationService(
            text_model_config=ModelConfig("test-text", ModelType.TEXT),
            vision_model_config=ModelConfig("test-vision", ModelType.VISION),
        )

        options = OrganizeOptions(
            generate_tags=True,
            tag_style="descriptive",
            tag_prompt="focus on main topic",
            enable_vision=True,
            parallel_workers=1,
            prefetch_depth=0,
        )
        request = OrganizeRequest(
            input_path=input_dir,
            output_path=output_dir,
            options=options,
        )

        result = service.preview(request)
        plan = result.plan
        assert plan is not None

        assert plan.total_files == 2
        assert len(plan.operations) == 2

        ops_by_filename = {op.file_name: op for op in plan.operations}

        assert "notes.txt" in ops_by_filename
        assert ops_by_filename["notes.txt"].tags == ["sprint", "planning", "weekly-notes"]

        # Image operation has generated filename
        image_ops = [op for op in plan.operations if op.source_path.endswith(".jpg")]
        assert len(image_ops) == 1
        assert image_ops[0].tags == ["landscape", "green", "outdoor"]


def test_organize_tagging_disabled_leaves_tags_empty(test_environment: tuple[Path, Path]) -> None:
    input_dir, output_dir = test_environment

    fake_text_model = MagicMock()
    fake_text_model.config.model_type = ModelType.TEXT
    fake_text_model.is_initialized = True
    fake_text_model.generate.return_value = "summary"

    fake_vision_model = MagicMock()
    fake_vision_model.config.model_type = ModelType.VISION
    fake_vision_model.is_initialized = True
    fake_vision_model.generate_structured.return_value = TaggedVisionSchema(
        description="Green landscape view",
        folder_name="nature",
        filename="green_landscape",
        has_text=False,
        tags=["should-not-be-used"],
    )

    with (
        patch(
            "file_organizer.services.text_processor.get_text_model", return_value=fake_text_model
        ),
        patch(
            "file_organizer.services.vision_processor.get_vision_model",
            return_value=fake_vision_model,
        ),
    ):
        service = OrganizationService(
            text_model_config=ModelConfig("test-text", ModelType.TEXT),
            vision_model_config=ModelConfig("test-vision", ModelType.VISION),
        )

        options = OrganizeOptions(
            generate_tags=False,
            enable_vision=True,
            parallel_workers=1,
            prefetch_depth=0,
        )
        request = OrganizeRequest(
            input_path=input_dir,
            output_path=output_dir,
            options=options,
        )

        result = service.preview(request)
        plan = result.plan
        assert plan is not None

        for op in plan.operations:
            assert op.tags == []


def test_file_organizer_direct_organize_with_tags_and_display(
    test_environment: tuple[Path, Path],
) -> None:
    input_dir, output_dir = test_environment

    fake_text_model = MagicMock()
    fake_text_model.config.model_type = ModelType.TEXT
    fake_text_model.is_initialized = True
    fake_text_model.generate_structured.return_value = TextAnalysisSchema(
        description="Meeting notes.",
        tags=["notes", "team"],
    )
    fake_text_model.generate.return_value = "folder"

    fake_vision_model = MagicMock()
    fake_vision_model.config.model_type = ModelType.VISION
    fake_vision_model.is_initialized = True
    fake_vision_model.generate_structured.return_value = TaggedVisionSchema(
        description="Green landscape",
        folder_name="images",
        filename="green_photo",
        has_text=False,
        tags=["photo", "green"],
    )

    with (
        patch(
            "file_organizer.services.text_processor.get_text_model", return_value=fake_text_model
        ),
        patch(
            "file_organizer.services.vision_processor.get_vision_model",
            return_value=fake_vision_model,
        ),
    ):
        organizer = FileOrganizer(
            text_model_config=ModelConfig("test-text", ModelType.TEXT),
            vision_model_config=ModelConfig("test-vision", ModelType.VISION),
            dry_run=True,
            parallel_workers=1,
            prefetch_depth=0,
            generate_tags=True,
            tag_style="descriptive",
            tag_prompt="keywords only",
        )

        result = organizer.organize(input_dir, output_dir)

        assert result.plan is not None
        assert len(result.plan.operations) == 2

        # Check display output renders tags
        console = MagicMock()
        show_summary(console, result, output_dir, dry_run=True)
        printed = "\n".join(str(c[0][0]) for c in console.print.call_args_list if c[0])

        assert "[dim](" in printed
        assert "notes, team" in printed
        assert "photo, green" in printed
