"""盘古 MCP Handler — multimodal (17 tools)"""
import json

TOOLS = [
    {"name": "pangu_ingest_file", "description": "\u4ece\u6587\u4ef6\u63d0\u53d6\u591a\u6a21\u6001\u8bb0\u5fc6\uff08\u56fe\u7247/PDF/\u6587\u672c/\u97f3\u9891\uff09"},
    {"name": "pangu_ingest_url", "description": "\u4eceURL\u6293\u53d6\u7f51\u9875\u5185\u5bb9\u5b58\u5165\u8bb0\u5fc6"},
    {"name": "pangu_ingest_text", "description": "\u76f4\u63a5\u5b58\u5165\u6587\u672c\u8bb0\u5fc6\uff08\u652f\u6301\u81ea\u5b9a\u4e49\u6a21\u6001\u6807\u7b7e\uff09"},
    {"name": "pangu_image_embed", "description": "\u56fe\u7247CLIP\u5d4c\u5165+\u5206\u6790\uff08\u5c3a\u5bf8/\u989c\u8272/\u5206\u7c7b\uff09"},
    {"name": "pangu_image_classify", "description": "\u56fe\u7247\u96f6\u6837\u672c\u5206\u7c7b\uff08CLIP\uff09"},
    {"name": "pangu_image_search_by_text", "description": "\u4ee5\u6587\u641c\u56fe\uff08\u6587\u672c\u5339\u914d\u56fe\u7247\u8bb0\u5fc6\uff09"},
    {"name": "pangu_image_search_by_image", "description": "\u4ee5\u56fe\u641c\u56fe\uff08\u56fe\u7247\u5339\u914d\u56fe\u7247\u8bb0\u5fc6\uff09"},
    {"name": "pangu_video_ingest", "description": "\u4ece\u89c6\u9891\u63d0\u53d6\u8bb0\u5fc6\uff08\u5143\u6570\u636e+\u5173\u952e\u5e27+CLIP\u5206\u6790\uff09"},
    {"name": "pangu_video_metadata", "description": "\u63d0\u53d6\u89c6\u9891\u5143\u6570\u636e\uff08\u65f6\u957f/\u5206\u8fa8\u7387/\u7f16\u7801/\u5e27\u7387\uff09"},
    {"name": "pangu_video_frames", "description": "\u63d0\u53d6\u89c6\u9891\u5173\u952e\u5e27"},
    {"name": "pangu_audio_transcribe", "description": "\u97f3\u9891\u8bed\u97f3\u8f6c\u6587\u5b57\uff08Whisper\uff09"},
    {"name": "pangu_audio_metadata", "description": "\u63d0\u53d6\u97f3\u9891\u5143\u6570\u636e\uff08\u65f6\u957f/\u683c\u5f0f/\u91c7\u6837\u7387\uff09"},
    {"name": "pangu_audio_ingest", "description": "\u4ece\u97f3\u9891\u63d0\u53d6\u8bb0\u5fc6\uff08\u8f6c\u5199+\u5143\u6570\u636e+\u81ea\u52a8\u5165\u5e93\uff09"},
    {"name": "pangu_multimodal_search", "description": "\u8de8\u6a21\u6001\u7edf\u4e00\u641c\u7d22\uff08\u6587\u672c\u641c\u6240\u6709\u6a21\u6001\uff1a\u6587\u672c/\u56fe\u7247/\u89c6\u9891/\u97f3\u9891\uff09"},
    {"name": "pangu_multimodal_summary", "description": "\u8de8\u6a21\u6001\u7efc\u5408\u6458\u8981\uff08\u7efc\u5408\u6240\u6709\u6a21\u6001\u5185\u5bb9\u751f\u6210\u6458\u8981\uff09"},
    {"name": "pangu_summary_by_topic", "description": "\u6309\u4e3b\u9898\u805a\u5408\u591a\u6a21\u6001\u6458\u8981"},
    {"name": "pangu_summary_timeline", "description": "\u6309\u65f6\u95f4\u7ebf\u751f\u6210\u591a\u6a21\u6001\u6458\u8981"},
]

HANDLERS = {}

async def handle_ingest_file(server, drawers, arguments):
    """从文件提取多模态记忆（图片/PDF/文本/音频）"""
    from ...memory.multimodal_pipeline import get_multimodal_pipeline
    pipe = get_multimodal_pipeline(server.config)
    result = pipe.ingest_file(
        arguments["file_path"],
        wing=arguments.get("wing", "default"),
        description=arguments.get("description", ""),
        tags=arguments.get("tags", []),
    )
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_ingest_file"] = handle_ingest_file

async def handle_ingest_url(server, drawers, arguments):
    """从URL抓取网页内容存入记忆"""
    from ...memory.multimodal_pipeline import get_multimodal_pipeline
    pipe = get_multimodal_pipeline(server.config)
    result = pipe.ingest_url(
        arguments["url"],
        wing=arguments.get("wing", "default"),
        description=arguments.get("description", ""),
        tags=arguments.get("tags", []),
    )
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_ingest_url"] = handle_ingest_url

async def handle_ingest_text(server, drawers, arguments):
    """直接存入文本记忆（支持自定义模态标签）"""
    from ...memory.multimodal_pipeline import get_multimodal_pipeline
    pipe = get_multimodal_pipeline(server.config)
    result = pipe.ingest_text(
        arguments["text"],
        wing=arguments.get("wing", "default"),
        description=arguments.get("description", ""),
        tags=arguments.get("tags", []),
        modality=arguments.get("modality", "text"),
    )
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_ingest_text"] = handle_ingest_text

async def handle_image_embed(server, drawers, arguments):
    """图片CLIP嵌入+分析（尺寸/颜色/分类）"""
    from ...memory.image_engine import get_image_engine
    engine = get_image_engine(server.config)
    result = engine.embed_image(arguments["image_path"])
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_image_embed"] = handle_image_embed

async def handle_image_classify(server, drawers, arguments):
    """图片零样本分类（CLIP）"""
    from ...memory.image_engine import get_image_engine
    engine = get_image_engine(server.config)
    result = engine.classify_image(arguments["image_path"])
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_image_classify"] = handle_image_classify

async def handle_image_search_by_text(server, drawers, arguments):
    """以文搜图（文本匹配图片记忆）"""
    from ...memory.image_engine import get_image_engine
    engine = get_image_engine(server.config)
    results = engine.search_by_text(arguments["query"], drawers, limit=arguments.get("limit", 5))
    return json.dumps({"count": len(results), "results": results}, ensure_ascii=False, indent=2)

HANDLERS["pangu_image_search_by_text"] = handle_image_search_by_text

async def handle_image_search_by_image(server, drawers, arguments):
    """以图搜图（图片匹配图片记忆）"""
    from ...memory.image_engine import get_image_engine
    engine = get_image_engine(server.config)
    results = engine.search_by_image(arguments["image_path"], drawers, limit=arguments.get("limit", 5))
    return json.dumps({"count": len(results), "results": results}, ensure_ascii=False, indent=2)

HANDLERS["pangu_image_search_by_image"] = handle_image_search_by_image

async def handle_video_ingest(server, drawers, arguments):
    """从视频提取记忆（元数据+关键帧+CLIP分析）"""
    from ...memory.video_engine import get_video_engine
    engine = get_video_engine(server.config)
    result = engine.ingest_video(
        arguments["video_path"],
        wing=arguments.get("wing", "default"),
        description=arguments.get("description", ""),
        tags=arguments.get("tags", []),
    )
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_video_ingest"] = handle_video_ingest

async def handle_video_metadata(server, drawers, arguments):
    """提取视频元数据（时长/分辨率/编码/帧率）"""
    from ...memory.video_engine import get_video_engine
    engine = get_video_engine(server.config)
    result = engine.get_metadata(arguments["video_path"])
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_video_metadata"] = handle_video_metadata

async def handle_video_frames(server, drawers, arguments):
    """提取视频关键帧"""
    from ...memory.video_engine import get_video_engine
    engine = get_video_engine(server.config)
    frames = engine.extract_keyframes(arguments["video_path"], count=arguments.get("count", 5))
    return json.dumps({"count": len(frames), "frames": frames}, ensure_ascii=False, indent=2)

HANDLERS["pangu_video_frames"] = handle_video_frames

async def handle_audio_transcribe(server, drawers, arguments):
    """音频语音转文字（Whisper）"""
    from ...memory.audio_engine import get_audio_engine
    engine = get_audio_engine(server.config)
    result = engine.transcribe(
        arguments["audio_path"],
        language=arguments.get("language"),
    )
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_audio_transcribe"] = handle_audio_transcribe

async def handle_audio_metadata(server, drawers, arguments):
    """提取音频元数据（时长/格式/采样率）"""
    from ...memory.audio_engine import get_audio_engine
    engine = get_audio_engine(server.config)
    result = engine.get_metadata(arguments["audio_path"])
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_audio_metadata"] = handle_audio_metadata

async def handle_audio_ingest(server, drawers, arguments):
    """从音频提取记忆（转写+元数据+自动入库）"""
    from ...memory.audio_engine import get_audio_engine
    engine = get_audio_engine(server.config)
    result = engine.ingest_audio(
        arguments["audio_path"],
        wing=arguments.get("wing", "default"),
        description=arguments.get("description", ""),
        tags=arguments.get("tags", []),
    )
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_audio_ingest"] = handle_audio_ingest

async def handle_multimodal_search(server, drawers, arguments):
    """跨模态统一搜索（文本搜所有模态：文本/图片/视频/音频）"""
    from ...memory.multimodal_search import get_multimodal_search
    engine = get_multimodal_search(server.config)
    result = engine.search(
        arguments["query"],
        drawers=drawers,
        modalities=arguments.get("modalities"),
        limit=arguments.get("limit", 10),
    )
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_multimodal_search"] = handle_multimodal_search

async def handle_multimodal_summary(server, drawers, arguments):
    """跨模态综合摘要（综合所有模态内容生成摘要）"""
    from ...memory.multimodal_summary import get_multimodal_summary
    engine = get_multimodal_summary(server.config)
    result = engine.summarize_memories(drawers, limit=arguments.get("limit", 50))
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_multimodal_summary"] = handle_multimodal_summary

async def handle_summary_by_topic(server, drawers, arguments):
    """按主题聚合多模态摘要"""
    from ...memory.multimodal_summary import get_multimodal_summary
    engine = get_multimodal_summary(server.config)
    result = engine.summarize_by_topic(drawers, arguments["topic"], limit=arguments.get("limit", 20))
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_summary_by_topic"] = handle_summary_by_topic

async def handle_summary_timeline(server, drawers, arguments):
    """按时间线生成多模态摘要"""
    from ...memory.multimodal_summary import get_multimodal_summary
    engine = get_multimodal_summary(server.config)
    result = engine.summarize_timeline(drawers, days=arguments.get("days", 7))
    return json.dumps(result, ensure_ascii=False, indent=2)

HANDLERS["pangu_summary_timeline"] = handle_summary_timeline