# Intelligent Routing Data Consistency Fix Plan

## Version Information
- **Created**: 2024-04-29
- **Status**: Pending Review
- **Priority**: P0

---

## Part 1: Problem Analysis

### 1.1 Current Problems

**Problem 1: Data Contamination**
- Executive Summary section contains Market Overview and Research Conclusions content
- Research Conclusions section contains Executive Summary content
- Cause: synthesis agents received results from other synthesis agents

**Problem 2: Data Inconsistency**
- Different sections independently search for the same entity (e.g., "BYD")
- Each section's "BYD revenue" data may differ
- Cause: No shared data pool, no cross-section dependencies

**Problem 3: Duplicate Searches**
- Multiple agents repeatedly search for the same keyword
- Wastes API calls and time
- Cause: No search result caching

### 1.2 Root Cause

```
Current data flow (problematic):

┌─────────────────┐     ┌─────────────────┐
│ Agent A         │     │ Agent B         │
│ (Company        │     │ (Competitive    │
│  Analysis)      │     │  Analysis)      │
├─────────────────┤     ├─────────────────┤
│ Search "BYD"   │     │ Search "BYD"   │  ← Duplicate search
│ Get: rev 500B  │     │ Get: rev 480B  │  ← Inconsistent data
│ Analysis: ...  │     │ Analysis: ...  │
└─────────────────┘     └─────────────────┘
         ↓                       ↓
    [Independent Result]   [Independent Result]
         ↓                       ↓
    ┌─────────────────────────────────┐
    │ Synthesis Agent                  │
    │ Receives two inconsistent sets   │
    │ → Contamination!                 │
    └─────────────────────────────────┘
```

### 1.3 Expected Behavior

```
Expected data flow (after fix):

┌─────────────────┐
│ Agent A         │
│ (Company        │
│  Analysis)      │
├─────────────────┤
│ Search "BYD"   │
│ Get: rev 500B  │
│ Store in shared │ ← New
│ data pool       │
└─────────────────┘
         ↓
    [Shared Data Pool]
    {BYD: {revenue: 500B, ...}}
         ↓
┌─────────────────┐
│ Agent B         │
│ (Competitive    │
│  Analysis)      │
├─────────────────┤
│ Depends on: A  │ ← New: cross-section dependency
│ Get from pool  │ ← New: data reuse
│ Reuse: rev 500B│
│ Analysis: ...  │
└─────────────────┘
         ↓
    [Consistent Data]
         ↓
    ┌─────────────────────────────────┐
    │ Synthesis Agent                  │
    │ Receives consistent data        │
    │ → No contamination!             │
    └─────────────────────────────────┘
```

---

## Part 2: Solution

### 2.1 Solution Overview

**Three-layer Fix**:
1. **Dependency Layer**: Intelligent routing correctly sets section dependency relationships
2. **Data Layer**: Shared data pool + search result cache
3. **Execution Layer**: Dependency-based data passing

### 2.2 Architecture Design

```
┌─────────────────────────────────────────────────────────────────┐
│                    Intelligent Routing System Architecture        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Task Decomposition Layer (TaskDecompositionStrategy)         │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ - Identify base vs derived sections                          ││
│  │ - Set cross-section dependency relationships                 ││
│  │ - Generate AgentSpec with dependencies                       ││
│  └─────────────────────────────────────────────────────────────┘│
│                              ↓                                  │
│                                                                  │
│  2. Data Sharing Layer (SharedDataPool) ← New                   │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ - Entity data cache (company info, market data)              ││
│  │ - Search result cache (avoid duplicate searches)             ││
│  │ - Data version control (ensure consistency)                  ││
│  └─────────────────────────────────────────────────────────────┘│
│                              ↓                                  │
│                                                                  │
│  3. Execution Layer (ExecutionEngine)                            │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │ - Filter data based on dependencies                          ││
│  │ - Pass shared data to derived sections                       ││
│  │ - Ensure data consistency                                    ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Part 3: Detailed Design

### 3.1 Section Dependency Definition

```python
# Section types
class SectionType(Enum):
    FOUNDATION = "foundation"      # Base sections (Market Overview, Company Analysis)
    DERIVED = "derived"           # Derived sections (Competitive Landscape, Market Share)
    SYNTHESIS = "synthesis"       # Synthesis sections (Executive Summary, Research Conclusions)

# Dependency rules
SECTION_DEPENDENCY_RULES = {
    # Derived sections depend on base sections
    "competitive landscape": ["company analysis", "market overview"],
    "market share": ["company analysis", "market size"],
    "investment analysis": ["company analysis", "competitive landscape"],
    
    # Synthesis sections depend on all analysis sections
    "executive summary": ["*"],  # Depends on all
    "research conclusions": ["*"],  # Depends on all
}
```

### 3.2 Shared Data Pool Design

```python
class SharedDataPool:
    """
    Shared Data Pool
    
    Stores data shared between sections, ensuring consistency.
    """
    
    def __init__(self):
        # Entity data (companies, products, etc.)
        self._entity_data: Dict[str, Dict[str, Any]] = {}
        
        # Search result cache
        self._search_cache: Dict[str, List[Dict]] = {}
        
        # Section output data
        self._section_outputs: Dict[str, Dict[str, Any]] = {}
    
    def store_entity(self, entity_name: str, data: Dict[str, Any], source_section: str) -> None:
        """Store entity data (with source tracking)"""
        if entity_name not in self._entity_data:
            self._entity_data[entity_name] = {
                "data": data,
                "source_section": source_section,
                "timestamp": datetime.now(),
            }
    
    def get_entity(self, entity_name: str) -> Optional[Dict[str, Any]]:
        """Get entity data"""
        return self._entity_data.get(entity_name, {}).get("data")
    
    def cache_search(self, query: str, results: List[Dict]) -> None:
        """Cache search results"""
        self._search_cache[query] = results
    
    def get_cached_search(self, query: str) -> Optional[List[Dict]]:
        """Get cached search results"""
        return self._search_cache.get(query)
    
    def store_section_output(self, section_id: str, output: Dict[str, Any]) -> None:
        """Store section output"""
        self._section_outputs[section_id] = output
    
    def get_section_outputs(self, section_ids: List[str]) -> Dict[str, Any]:
        """Get outputs from multiple sections"""
        return {
            sid: self._section_outputs.get(sid, {})
            for sid in section_ids
            if sid in self._section_outputs
        }
```

[Content continues with section 3.3 Task Decomposition Strategy Improvement, 3.4 Execution Engine Improvement, 3.5 GenericAgent Improvement, etc.]
