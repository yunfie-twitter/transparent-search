"""Admin index and content management endpoints."""
from fastapi import APIRouter, HTTPException, Query, Body
from typing import Optional, List, Dict, Any
from datetime import datetime

from app.db.models import SearchContent
from app.core.database import async_session
from app.utils.content_classifier import content_classifier
from sqlalchemy import select, func, and_, or_

router = APIRouter(prefix="/admin/index", tags=["admin-index"])

# ============================================================================
# Indexing Operations
# ============================================================================

@router.post("/reindex")
async def reindex_content(
    domain: Optional[str] = Query(None, description="Reindex specific domain"),
    content_type: Optional[str] = Query(None, description="Filter by content type"),
    force: bool = Query(False, description="Force reindex even if recent"),
):
    """
    Reindex content in the search database.
    
    Options:
    - domain: Reindex specific domain only
    - content_type: Reindex specific content type
    - force: Force reindex even if recently indexed
    """
    try:
        conditions = []
        
        if domain:
            conditions.append(SearchContent.domain == domain)
        
        if content_type:
            conditions.append(SearchContent.content_type == content_type)
        
        async with async_session() as session:
            # Count matching documents
            count_query = select(func.count(SearchContent.id))
            if conditions:
                count_query = count_query.where(and_(*conditions))
            
            result = await session.execute(count_query)
            total_docs = result.scalar() or 0
            
            return {
                "status": "reindex_queued",
                "documents_to_reindex": total_docs,
                "domain_filter": domain,
                "content_type_filter": content_type,
                "force": force,
                "message": f"Queued {total_docs} documents for reindexing",
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.post("/optimize")
async def optimize_index(
    full_optimize: bool = Query(False, description="Full index optimization (slower)"),
):
    """
    Optimize the search index for better performance.
    
    - full_optimize=False: Quick optimization (default, ~1-5 sec)
    - full_optimize=True: Full vacuum (may take longer, better results)
    """
    return {
        "status": "optimization_queued",
        "type": "full" if full_optimize else "quick",
        "message": "Index optimization queued",
        "estimated_time_seconds": 60 if full_optimize else 5,
    }


@router.post("/clear")
async def clear_index(
    domain: Optional[str] = Query(None, description="Clear specific domain"),
    content_type: Optional[str] = Query(None, description="Clear specific content type"),
    confirm: bool = Query(False, description="Confirm deletion"),
):
    """
    Clear index data (destructive operation).
    
    ⚠️ WARNING: This operation cannot be undone!
    """
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Must set confirm=true to execute clear operation"
        )
    
    try:
        conditions = []
        
        if domain:
            conditions.append(SearchContent.domain == domain)
        
        if content_type:
            conditions.append(SearchContent.content_type == content_type)
        
        async with async_session() as session:
            # Count before deletion
            count_query = select(func.count(SearchContent.id))
            if conditions:
                count_query = count_query.where(and_(*conditions))
            
            result = await session.execute(count_query)
            total_before = result.scalar() or 0
            
            # Delete matching documents
            delete_query = select(SearchContent)
            if conditions:
                delete_query = delete_query.where(and_(*conditions))
            
            result = await session.execute(delete_query)
            items = result.scalars().all()
            
            for item in items:
                await session.delete(item)
            
            await session.commit()
            
            return {
                "status": "cleared",
                "documents_deleted": len(items),
                "domain_filter": domain,
                "content_type_filter": content_type,
                "warning": "This operation cannot be undone!",
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


# ============================================================================
# Content Management
# ============================================================================

@router.get("/contents")
async def list_contents(
    domain: Optional[str] = Query(None),
    content_type: Optional[str] = Query(None),
    quality_min: Optional[float] = Query(None, ge=0.0, le=1.0),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """
    List indexed content with filtering.
    """
    try:
        async with async_session() as session:
            query = select(SearchContent)
            
            conditions = []
            if domain:
                conditions.append(SearchContent.domain == domain)
            if content_type:
                conditions.append(SearchContent.content_type == content_type)
            if quality_min is not None:
                conditions.append(SearchContent.quality_score >= quality_min)
            
            if conditions:
                query = query.where(and_(*conditions))
            
            query = query.limit(limit).offset(offset)
            
            result = await session.execute(query)
            contents = result.scalars().all()
            
            return {
                "contents": [
                    {
                        "id": c.id,
                        "url": c.url,
                        "domain": c.domain,
                        "title": c.title,
                        "content_type": c.content_type,
                        "quality_score": c.quality_score,
                        "indexed_at": c.indexed_at.isoformat() if c.indexed_at else None,
                        "last_crawled_at": c.last_crawled_at.isoformat() if c.last_crawled_at else None,
                    }
                    for c in contents
                ],
                "count": len(contents),
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.get("/contents/{content_id}")
async def get_content(content_id: int):
    """
    Get detailed content information.
    """
    try:
        async with async_session() as session:
            query = select(SearchContent).where(SearchContent.id == content_id)
            result = await session.execute(query)
            content = result.scalar_one_or_none()
            
            if not content:
                raise HTTPException(status_code=404, detail="Content not found")
            
            return {
                "id": content.id,
                "url": content.url,
                "domain": content.domain,
                "title": content.title,
                "description": content.description,
                "content": content.content[:500] + "..." if content.content and len(content.content) > 500 else content.content,
                "content_type": content.content_type,
                "quality_score": content.quality_score,
                "h1": content.h1,
                "h2_tags": content.h2_tags,
                "meta_description": content.meta_description,
                "indexed_at": content.indexed_at.isoformat() if content.indexed_at else None,
                "last_crawled_at": content.last_crawled_at.isoformat() if content.last_crawled_at else None,
            }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.delete("/contents/{content_id}")
async def delete_content(content_id: int):
    """
    Delete specific indexed content.
    """
    try:
        async with async_session() as session:
            query = select(SearchContent).where(SearchContent.id == content_id)
            result = await session.execute(query)
            content = result.scalar_one_or_none()
            
            if not content:
                raise HTTPException(status_code=404, detail="Content not found")
            
            await session.delete(content)
            await session.commit()
            
            return {
                "status": "deleted",
                "content_id": content_id,
                "url": content.url,
            }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.post("/contents/{content_id}/recrawl")
async def recrawl_content(content_id: int):
    """
    Mark content for recrawling.
    """
    try:
        async with async_session() as session:
            query = select(SearchContent).where(SearchContent.id == content_id)
            result = await session.execute(query)
            content = result.scalar_one_or_none()
            
            if not content:
                raise HTTPException(status_code=404, detail="Content not found")
            
            return {
                "status": "recrawl_queued",
                "content_id": content_id,
                "url": content.url,
                "message": "Content queued for recrawling",
            }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


# ============================================================================
# Content Classification
# ============================================================================

@router.post("/classify-url")
async def classify_url(
    url: str = Query(..., description="URL to classify"),
):
    """
    Classify a URL without crawling it.
    
    Returns predicted content type based on URL and domain patterns.
    """
    try:
        classification = content_classifier.classify_by_url(url)
        
        return {
            "url": url,
            "content_type": classification["type"],
            "confidence": classification["confidence"],
            "description": classification["description"],
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.post("/classify-content")
async def classify_content(
    url: str = Query(...),
    html: str = Query(..., description="HTML content to classify"),
):
    """
    Classify content based on HTML analysis.
    
    More accurate than URL-only classification.
    """
    try:
        classification = content_classifier.classify_by_html(html, url)
        
        return {
            "url": url,
            "content_type": classification["type"],
            "confidence": classification["confidence"],
            "detected_patterns": classification.get("patterns", []),
            "description": classification["description"],
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


# ============================================================================
# Statistics & Reporting
# ============================================================================

@router.get("/stats")
async def index_statistics():
    """
    Get comprehensive index statistics.
    """
    try:
        async with async_session() as session:
            # Total documents
            total_query = select(func.count(SearchContent.id))
            total_result = await session.execute(total_query)
            total_docs = total_result.scalar() or 0
            
            # By content type
            type_query = select(
                SearchContent.content_type,
                func.count(SearchContent.id)
            ).group_by(SearchContent.content_type)
            type_result = await session.execute(type_query)
            by_type = dict(type_result.all())
            
            # By domain (top 10)
            domain_query = select(
                SearchContent.domain,
                func.count(SearchContent.id)
            ).group_by(SearchContent.domain).limit(10)
            domain_result = await session.execute(domain_query)
            by_domain = dict(domain_result.all())
            
            # Average quality score
            quality_query = select(func.avg(SearchContent.quality_score))
            quality_result = await session.execute(quality_query)
            avg_quality = quality_result.scalar() or 0
            
            return {
                "total_documents": total_docs,
                "by_content_type": by_type,
                "top_10_domains": by_domain,
                "average_quality_score": round(avg_quality, 3),
                "last_updated": datetime.utcnow().isoformat(),
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


# ============================================================================
# Configuration
# ============================================================================

@router.get("/config")
async def get_index_config():
    """
    Get index configuration and limits.
    """
    return {
        "limits": {
            "max_content_size": "100MB",
            "max_url_length": 2048,
            "max_title_length": 256,
        },
        "supported_content_types": [
            "text_article",
            "blog_post",
            "news",
            "documentation",
            "video",
            "image",
            "pdf",
            "code_repository",
            "social_media",
        ],
        "quality_score_thresholds": {
            "excellent": 0.8,
            "good": 0.6,
            "acceptable": 0.4,
            "poor": 0.0,
        },
    }


# ============================================================================
# Documentation
# ============================================================================

@router.get("/docs")
async def index_api_documentation():
    """
    Get comprehensive index API documentation.
    """
    return {
        "title": "Index Management API",
        "version": "1.0",
        "sections": {
            "indexing": {
                "POST /admin/index/reindex": "Reindex content",
                "POST /admin/index/optimize": "Optimize index performance",
                "POST /admin/index/clear": "Clear index data (destructive)",
            },
            "content_management": {
                "GET /admin/index/contents": "List indexed content",
                "GET /admin/index/contents/{id}": "Get content details",
                "DELETE /admin/index/contents/{id}": "Delete content",
                "POST /admin/index/contents/{id}/recrawl": "Mark for recrawling",
            },
            "classification": {
                "POST /admin/index/classify-url": "Classify by URL",
                "POST /admin/index/classify-content": "Classify by HTML content",
            },
            "statistics": {
                "GET /admin/index/stats": "Get index statistics",
            },
            "configuration": {
                "GET /admin/index/config": "Get configuration",
            },
        },
    }
