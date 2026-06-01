# Zensers REST API Specification

> **Status**: Design Phase | **Version**: v1.0 | **Base URL**: `https://api.Zensers.io/v1`

## 1. Overview

This document defines the REST API interface specification for Zensers cloud deployment. All interfaces follow these conventions:

### 1.1 General Conventions

| Item | Convention |
|------|-----------|
| Protocol | HTTPS only |
| Data Format | JSON |
| Character Encoding | UTF-8 |
| Time Format | ISO 8601 (UTC) |
| Pagination | `?page=1&page_size=20` |
| Authentication | Bearer Token (JWT) |
