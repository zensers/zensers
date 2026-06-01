# -*- coding: utf-8 -*-
"""
Document Quality Validator
==========================

Performs final checks after document generation to ensure no low-level issues.

Checklist:
1. Template syntax residuals ({% %}, {{ }})
2. CSS code leakage (/*, @page, @media)
3. HTML tag residuals (<style>, <script>)
4. Content depth (minimum character count)
5. Structural integrity (must have headings and content)
"""

import re
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Validation result"""
    valid: bool
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    stats: Dict[str, int] = field(default_factory=dict)


class DocumentQualityValidator:
    """
    Document Quality Validator
    
    Checks after document generation to prevent low-level issues from reaching the final output.
    """
    
    # Template syntax patterns
    TEMPLATE_PATTERNS = [
        (r'\{%\s*for\s+', 'Unrendered loop start tag'),
        (r'\{%\s*endfor\s*%\}', 'Unrendered loop end tag'),
        (r'\{%\s*if\s+', 'Unrendered condition start tag'),
        (r'\{%\s*endif\s*%\}', 'Unrendered condition end tag'),
        (r'\{%\s*else\s*%\}', 'Unrendered else tag'),
        (r'\{\{\s*\w+', 'Unrendered variable tag'),
        (r'%\}', 'Residual template end marker'),
    ]
    
    # CSS leakage patterns
    CSS_PATTERNS = [
        (r'/\*', 'CSS comment marker'),
        (r'\*/', 'CSS comment end marker'),
        (r'@page\s*\{', 'CSS page rule'),
        (r'@media\s+', 'CSS media query'),
        (r'@import\s+', 'CSS import'),
        (r'font-family:\s*["\']', 'CSS font declaration'),
        (r'background(-color)?:', 'CSS background property'),
        (r'padding:\s*\d+', 'CSS padding'),
        (r'margin:\s*\d+', 'CSS margin'),
    ]
    
    # HTML tag leakage patterns
    HTML_PATTERNS = [
        (r'<style[^>]*>', 'HTML style tag'),
        (r'</style>', 'HTML style end tag'),
        (r'<script[^>]*>', 'HTML script tag'),
        (r'</script>', 'HTML script end tag'),
        (r'<head[^>]*>', 'HTML head tag'),
        (r'</head>', 'HTML head end tag'),
    ]
    
    # Minimum content requirements
    MIN_CONTENT_LENGTH = 500  # Minimum character count
    MIN_PARAGRAPHS = 3  # Minimum paragraph count
    MIN_WORDS = 50  # Minimum word count
    
    def validate(self, content: str, paragraphs: int = 0) -> ValidationResult:
        """
        Validate document content
        
        Args:
            content: Full document text
            paragraphs: Number of paragraphs
            
        Returns:
            ValidationResult
        """
        issues = []
        warnings = []
        stats = {}
        
        # 1. Check template syntax residuals
        template_issues = self._check_patterns(content, self.TEMPLATE_PATTERNS)
        if template_issues:
            issues.extend([f"Template syntax residual: {issue}" for issue in template_issues])
        
        # 2. Check CSS leakage
        css_issues = self._check_patterns(content, self.CSS_PATTERNS)
        if css_issues:
            issues.extend([f"CSS code leakage: {issue}" for issue in css_issues])
        
        # 3. Check HTML tag leakage
        html_issues = self._check_patterns(content, self.HTML_PATTERNS)
        if html_issues:
            issues.extend([f"HTML tag leakage: {issue}" for issue in html_issues])
        
        # 4. Check content depth
        content_length = len(content.strip())
        word_count = len(content.split())
        
        stats['content_length'] = content_length
        stats['word_count'] = word_count
        stats['paragraphs'] = paragraphs
        
        if content_length < self.MIN_CONTENT_LENGTH:
            warnings.append(f"Insufficient content depth: {content_length} < {self.MIN_CONTENT_LENGTH} chars")
        
        if word_count < self.MIN_WORDS:
            warnings.append(f"Insufficient word count: {word_count} < {self.MIN_WORDS}")
        
        if paragraphs < self.MIN_PARAGRAPHS:
            warnings.append(f"Insufficient paragraphs: {paragraphs} < {self.MIN_PARAGRAPHS}")
        
        # 5. Check structural integrity
        has_heading = bool(re.search(r'Chapter\s+\d+', content))
        has_content = content_length > 100
        
        if not has_heading:
            warnings.append("Missing chapter heading")
        
        if not has_content:
            issues.append("Document content is empty")
        
        # Overall judgment
        valid = len(issues) == 0
        
        result = ValidationResult(
            valid=valid,
            issues=issues,
            warnings=warnings,
            stats=stats
        )
        
        if not valid:
            logger.error(f"Document validation failed: {issues}")
        elif warnings:
            logger.warning(f"Document validation warnings: {warnings}")
        else:
            logger.info(f"Document validation passed: {stats}")
        
        return result
    
    def _check_patterns(self, content: str, patterns: List[Tuple[str, str]]) -> List[str]:
        """Check if content contains the specified patterns"""
        found = []
        for pattern, description in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                found.append(f"{description} (found {len(matches)})")
        return found
    
    def sanitize(self, content: str) -> str:
        """
        Clean up issues in the content (if possible)
        
        Args:
            content: Original content
            
        Returns:
            Sanitized content
        """
        # Remove unrendered template tags (preserve content)
        content = re.sub(r'\{%\s*for\s+\w+\s+in\s+\w+\s*%\}', '', content)
        content = re.sub(r'\{%\s*endfor\s*%\}', '', content)
        content = re.sub(r'\{%\s*if\s+[\w.]+\s*%\}', '', content)
        content = re.sub(r'\{%\s*endif\s*%\}', '', content)
        content = re.sub(r'\{%\s*else\s*%\}', '', content)
        content = re.sub(r'\{\{\s*[\w.]+\s*\}\}', '', content)
        
        # Remove residual %} markers
        content = re.sub(r'%\}', '', content)
        
        return content.strip()


# Global validator instance
_validator = DocumentQualityValidator()


def validate_document(content: str, paragraphs: int = 0) -> ValidationResult:
    """Validate document content (convenience function)"""
    return _validator.validate(content, paragraphs)


def sanitize_document(content: str) -> str:
    """Sanitize document content (convenience function)"""
    return _validator.sanitize(content)
