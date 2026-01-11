"""Admin crawl management endpoints."""
from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Form
from typing import Optional, List, Dict, Any
from datetime import datetime
import csv
import json
import io

from app.db.models import CrawlSession, CrawlJob
from app.core.database import get_db_session
from app.services.crawler import crawler_service
from sqlalchemy import select, func, and_

router = APIRouter(prefix="/admin/crawl", tags=["admin-crawl"])


@router.post("/bulk-import")
async def bulk_import_urls(
    file: UploadFile = File(..., description="URL list file (CSV, JSON, or TXT)"),
    domain: Optional[str] = Query(None, description="Filter/validate URLs to specific domain"),
    max_depth: int = Query(3, ge=1, le=15, description="Max crawl depth"),
    session_id: Optional[str] = Query(None, description="Add to existing session (optional)"),
):
    """
    Bulk import URLs for crawling from file.
    
    Supported formats:
    - CSV: url,domain (header optional)
    - JSON: [{"url": "...", "domain": "..."}, ...] or ["url1", "url2", ...]
    - TXT: one URL per line
    
    Args:
        file: Upload file containing URLs
        domain: Optional domain filter (only crawl URLs from this domain)
        max_depth: Maximum crawl depth for jobs
        session_id: Optional existing session ID to add jobs to
    
    Returns:
        Import statistics and created session/jobs info
    """
    try:
        # Read file content
        content = await file.read()
        filename = file.filename or "unknown"
        
        # Parse file based on extension
        urls_to_crawl = []
        
        if filename.endswith('.csv'):
            # Parse CSV
            lines = content.decode('utf-8').split('\n')
            reader = csv.reader(lines)
            
            # Check if first line is header
            first_row = next(reader, None)
            if first_row and (first_row[0].lower() == 'url' or first_row[0].lower() == 'link'):
                # Skip header
                pass
            elif first_row:
                # First row is data
                url = first_row[0].strip()
                if url:
                    urls_to_crawl.append({
                        "url": url,
                        "domain": first_row[1].strip() if len(first_row) > 1 else None,
                    })
            
            # Process remaining rows
            for row in reader:
                if row and row[0].strip():
                    url = row[0].strip()
                    urls_to_crawl.append({
                        "url": url,
                        "domain": row[1].strip() if len(row) > 1 else None,
                    })
        
        elif filename.endswith('.json'):
            # Parse JSON
            data = json.loads(content.decode('utf-8'))
            
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        url = item.get('url') or item.get('link')
                        domain = item.get('domain')
                        if url:
                            urls_to_crawl.append({"url": url, "domain": domain})
                    elif isinstance(item, str):
                        if item.strip():
                            urls_to_crawl.append({"url": item.strip(), "domain": None})
        
        else:
            # Parse as plain text (one URL per line)
            lines = content.decode('utf-8').split('\n')
            for line in lines:
                url = line.strip()
                if url and not url.startswith('#'):
                    urls_to_crawl.append({"url": url, "domain": None})
        
        if not urls_to_crawl:
            raise HTTPException(status_code=400, detail="No valid URLs found in file")
        
        # Extract domains from URLs if not provided
        from urllib.parse import urlparse
        processed_urls = []
        
        for item in urls_to_crawl:
            url = item["url"]
            
            # Validate URL format
            if not url.startswith(('http://', 'https://')):
                url = f"https://{url}"
            
            try:
                parsed = urlparse(url)
                extracted_domain = parsed.netloc
            except Exception:
                continue
            
            # Apply domain filter if specified
            if domain and extracted_domain != domain and not extracted_domain.endswith(f".{domain}"):
                continue
            
            processed_urls.append({
                "url": url,
                "domain": item.get("domain") or extracted_domain,
            })
        
        if not processed_urls:
            raise HTTPException(
                status_code=400,
                detail=f"No URLs match domain filter: {domain}" if domain else "No valid URLs after processing"
            )
        
        # Group by domain
        domains_map: Dict[str, List[str]] = {}
        for item in processed_urls:
            d = item["domain"]
            if d not in domains_map:
                domains_map[d] = []
            domains_map[d].append(item["url"])
        
        # Create session or use existing
        async with get_db_session() as db:
            if session_id:
                # Use existing session
                from sqlalchemy import select
                stmt = select(CrawlSession).where(CrawlSession.session_id == session_id)
                result = await db.execute(stmt)
                session = result.scalar_one_or_none()
                if not session:
                    raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
            else:
                # Create new session for first domain
                first_domain = list(domains_map.keys())[0]
                session = await crawler_service.create_crawl_session(
                    domain=first_domain,
                    max_depth=max_depth,
                    page_limit=len(processed_urls),
                )
            
            # Create crawl jobs for each URL
            created_jobs = []
            failed_urls = []
            
            for domain_name, urls in domains_map.items():
                for url in urls:
                    try:
                        job = await crawler_service.create_crawl_job(
                            session_id=session.session_id,
                            domain=domain_name,
                            url=url,
                            depth=0,
                            max_depth=max_depth,
                            enable_js_rendering=False,
                        )
                        if job:
                            created_jobs.append({
                                "job_id": job.job_id,
                                "url": url,
                                "domain": domain_name,
                                "status": "pending",
                            })
                    except Exception as e:
                        failed_urls.append({"url": url, "error": str(e)})
            
            return {
                "status": "import_complete",
                "session_id": session.session_id,
                "session_created": session_id is None,
                "total_urls": len(processed_urls),
                "created_jobs": len(created_jobs),
                "failed_urls": len(failed_urls),
                "domains_count": len(domains_map),
                "max_depth": max_depth,
                "domain_breakdown": {
                    d: len(urls) for d, urls in domains_map.items()
                },
                "created_jobs_sample": created_jobs[:10],  # Return first 10 for reference
                "failed_urls_sample": failed_urls[:10] if failed_urls else None,
                "message": f"✅ Imported {len(created_jobs)} URLs for crawling" + (
                    f" (⚠️ {len(failed_urls)} failed)" if failed_urls else ""
                ),
            }
    
    except HTTPException:
        raise
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")


@router.post("/manual-urls")
async def crawl_manual_urls(
    urls: List[str] = Form(..., description="List of URLs to crawl"),
    max_depth: int = Query(3, ge=1, le=15, description="Max crawl depth"),
    session_id: Optional[str] = Query(None, description="Add to existing session"),
):
    """
    Crawl manually entered URLs.
    
    Args:
        urls: List of URLs (submitted as form data)
        max_depth: Maximum crawl depth
        session_id: Optional existing session ID
    
    Returns:
        Job creation statistics
    """
    if not urls:
        raise HTTPException(status_code=400, detail="URLs list cannot be empty")
    
    try:
        from urllib.parse import urlparse
        
        # Process URLs
        processed_urls = []
        for url in urls:
            url = url.strip()
            if not url:
                continue
            
            if not url.startswith(('http://', 'https://')):
                url = f"https://{url}"
            
            try:
                parsed = urlparse(url)
                if parsed.netloc:
                    processed_urls.append({
                        "url": url,
                        "domain": parsed.netloc,
                    })
            except Exception:
                pass
        
        if not processed_urls:
            raise HTTPException(status_code=400, detail="No valid URLs provided")
        
        # Group by domain
        domains_map: Dict[str, List[str]] = {}
        for item in processed_urls:
            d = item["domain"]
            if d not in domains_map:
                domains_map[d] = []
            domains_map[d].append(item["url"])
        
        async with get_db_session() as db:
            # Create or use session
            if session_id:
                stmt = select(CrawlSession).where(CrawlSession.session_id == session_id)
                result = await db.execute(stmt)
                session = result.scalar_one_or_none()
                if not session:
                    raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
            else:
                first_domain = list(domains_map.keys())[0]
                session = await crawler_service.create_crawl_session(
                    domain=first_domain,
                    max_depth=max_depth,
                    page_limit=len(processed_urls),
                )
            
            # Create jobs
            created_jobs = []
            
            for domain_name, urls_list in domains_map.items():
                for url in urls_list:
                    try:
                        job = await crawler_service.create_crawl_job(
                            session_id=session.session_id,
                            domain=domain_name,
                            url=url,
                            depth=0,
                            max_depth=max_depth,
                            enable_js_rendering=False,
                        )
                        if job:
                            created_jobs.append({
                                "job_id": job.job_id,
                                "url": url,
                                "domain": domain_name,
                            })
                    except Exception:
                        pass
            
            return {
                "status": "success",
                "session_id": session.session_id,
                "created_jobs": len(created_jobs),
                "domains_count": len(domains_map),
                "max_depth": max_depth,
                "message": f"✅ Created {len(created_jobs)} crawl jobs",
            }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating jobs: {str(e)}")


@router.get("/sessions")
async def list_crawl_sessions(
    domain: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """
    List crawl sessions with statistics.
    """
    try:
        async with get_db_session() as db:
            # Build query
            query = select(CrawlSession)
            
            if domain:
                query = query.where(CrawlSession.domain.ilike(f"%{domain}%"))
            
            # Get total
            count_query = select(func.count(CrawlSession.session_id))
            if domain:
                count_query = count_query.where(CrawlSession.domain.ilike(f"%{domain}%"))
            count_result = await db.execute(count_query)
            total = count_result.scalar() or 0
            
            # Get paginated results
            query = query.limit(limit).offset(offset)
            result = await db.execute(query)
            sessions = result.scalars().all()
            
            # Get job counts for each session
            session_data = []
            for session in sessions:
                job_count_stmt = select(func.count(CrawlJob.job_id)).where(
                    CrawlJob.session_id == session.session_id
                )
                job_count_result = await db.execute(job_count_stmt)
                job_count = job_count_result.scalar() or 0
                
                session_data.append({
                    "session_id": session.session_id,
                    "domain": session.domain,
                    "status": session.status,
                    "total_jobs": job_count,
                    "created_at": session.created_at.isoformat() if session.created_at else None,
                    "started_at": session.started_at.isoformat() if session.started_at else None,
                    "completed_at": session.completed_at.isoformat() if session.completed_at else None,
                })
            
            return {
                "meta": {
                    "total": total,
                    "count": len(session_data),
                    "limit": limit,
                    "offset": offset,
                },
                "sessions": session_data,
            }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.get("/sessions/{session_id}")
async def get_session_details(session_id: str):
    """
    Get detailed session information and job statistics.
    """
    try:
        stats = await crawler_service.crawl_worker.get_session_stats(session_id)
        
        if not stats:
            raise HTTPException(status_code=404, detail="Session not found")
        
        return {
            "status": "success",
            "session": stats,
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


__all__ = ["router"]
