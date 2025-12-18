import json
import dataclasses
import uuid
from pathlib import Path
from typing import Dict, Any

from core.models import ProjectData, NamedComposition, Composition, TieLine, GridSettings, VisualStyle
from core.constants import (
    GRID_STEP_DEFAULT, COLOR_DEFAULT_COMP, MARKER_SIZE_DEFAULT,
    COLOR_DEFAULT_LINE, LINE_WIDTH_DEFAULT
)
from loguru import logger  # <--- Импорт

class ProjectFileError(Exception):
    """Базовое исключение для операций с файлами проекта"""
    pass

class ProjectSerializer:
    @staticmethod
    def save_to_file(project: ProjectData, filepath: str) -> None:
        logger.info(f"Saving project to: {filepath}")
        try:
            data_dict = dataclasses.asdict(project)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data_dict, f, indent=4)
            logger.success("Project saved successfully")  # <--- У loguru есть уровень SUCCESS (зеленый)
        except Exception as e:
            # logger.exception сам запишет стек вызовов красиво
            logger.exception(f"Save failed: {filepath}") 
            raise ProjectFileError(f"Failed to save file: {e}")

    @staticmethod
    def load_from_file(filepath: str) -> ProjectData:
        logger.info(f"Loading project from: {filepath}")
        path = Path(filepath)
        if not path.exists():
            raise ProjectFileError(f"File not found: {path.name}")
            
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ProjectFileError(f"Invalid JSON format: {e.msg}")
        except Exception as e:
            raise ProjectFileError(f"Read error: {e}")
            
        return ProjectSerializer._parse_project_data(data)

    @staticmethod
    def _parse_project_data(data: Dict[str, Any]) -> ProjectData:
        """Парсит dict в ProjectData с проверками"""
        new_project = ProjectData()
        
        # Components
        comps = data.get("components", ["A", "B", "C"])
        if isinstance(comps, list) and len(comps) == 3:
            new_project.components = [str(c) for c in comps]
        
        new_project.is_inverted = bool(data.get("is_inverted", True))
        
        # Vertex positions
        v_pos = data.get("vertex_labels_pos", {})
        if isinstance(v_pos, dict):
            new_project.vertex_labels_pos = {
                k: tuple(v) for k, v in v_pos.items() 
                if isinstance(v, (list, tuple)) and len(v) == 2
            }
        
        # Grid
        g_data = data.get("grid", {})
        if isinstance(g_data, dict):
            new_project.grid = GridSettings(
                visible=bool(g_data.get("visible", False)),
                step=float(g_data.get("step", GRID_STEP_DEFAULT))
            )
        
        # Compositions
        for p_dict in data.get("compositions", []):
            if not isinstance(p_dict, dict):
                continue
            
            try:
                comp = ProjectSerializer._parse_composition(p_dict)
                new_project.compositions.append(comp)
            except (ValueError, TypeError, KeyError):
                continue  # Пропускаем битый состав
        
        # Lines
        comp_uids = {p.uid for p in new_project.compositions}
        
        for l_dict in data.get("lines", []):
            if not isinstance(l_dict, dict):
                continue
            
            try:
                line = ProjectSerializer._parse_line(l_dict)
                # Проверяем, что оба состава существуют
                if line.start_uid in comp_uids and line.end_uid in comp_uids:
                    new_project.lines.append(line)
            except (ValueError, TypeError, KeyError):
                continue  # Пропускаем битую линию
        
        return new_project

    @staticmethod
    def _parse_composition(p_dict: Dict[str, Any]) -> NamedComposition:
        """Парсит один состав"""
        comp_dict = p_dict.get("composition", {})
        style_dict = p_dict.get("style", {})
        
        label_offset = p_dict.get("label_offset")
        if label_offset is not None:
            label_offset = tuple(label_offset) if isinstance(label_offset, (list, tuple)) else None
        
        # Генерация UID если его нет
        raw_uid = p_dict.get("uid")
        if raw_uid:
            uid = str(raw_uid)
        else:
            uid = str(uuid.uuid4())

        return NamedComposition(
            uid=uid,
            name=str(p_dict.get("name", "")),
            composition=Composition(
                a=float(comp_dict.get("a", 0)),
                b=float(comp_dict.get("b", 0)),
                c=float(comp_dict.get("c", 0))
            ),
            style=ProjectSerializer._parse_style(style_dict, ProjectSerializer.COMP_STYLE_DEFAULTS),
            label_offset=label_offset
        )

    @staticmethod
    def _parse_line(l_dict: Dict[str, Any]) -> TieLine:
        """Парсит одну линию"""
        style_dict = l_dict.get("style", {})
        raw_uid = l_dict.get("uid")
        uid = str(raw_uid) if raw_uid else str(uuid.uuid4())

        return TieLine(
            uid=uid,
            start_uid=str(l_dict.get("start_uid", "")),
            end_uid=str(l_dict.get("end_uid", "")),
            style=ProjectSerializer._parse_style(style_dict, ProjectSerializer.LINE_STYLE_DEFAULTS)
        )
    
    @staticmethod
    def _parse_style(style_dict: dict, defaults: dict) -> VisualStyle:
        """Парсит стиль с дефолтными значениями"""
        return VisualStyle(
            color=str(style_dict.get("color", defaults.get("color", "#000000"))),
            size=float(style_dict.get("size", defaults.get("size", 8.0))),
            line_style=str(style_dict.get("line_style", defaults.get("line_style", "-"))),
            marker_symbol=str(style_dict.get("marker_symbol", defaults.get("marker_symbol", "o"))),
            show_label=bool(style_dict.get("show_label", defaults.get("show_label", True))),
            show_marker=bool(style_dict.get("show_marker", defaults.get("show_marker", True)))
        )

    # Константы для дефолтов
    COMP_STYLE_DEFAULTS = {
        "color": COLOR_DEFAULT_COMP,
        "size": MARKER_SIZE_DEFAULT,
        "marker_symbol": "o",
        "show_label": True,
        "show_marker": True
    }
    
    LINE_STYLE_DEFAULTS = {
        "color": COLOR_DEFAULT_LINE,
        "size": LINE_WIDTH_DEFAULT,
        "line_style": "-"
    }
