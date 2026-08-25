from __future__ import annotations

from typing import Any


def action_schema(public_base_url: str) -> dict[str, Any]:
    base = public_base_url.rstrip("/")
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Adinkra Omega NCA Telecom Analytics API",
            "version": "1.0.0",
            "description": (
                "Read-only, evidence-grounded analysis of monthly Ghana telecom operator data. "
                "Calculations are performed by the API and include source provenance, quality caveats, "
                "chart-ready data, and a human-review governance envelope."
            ),
        },
        "servers": [{"url": base}],
        "paths": {
            "/api/v1/health": {
                "get": {
                    "operationId": "checkTelecomAnalyticsHealth",
                    "summary": "Check whether the analytics service is available",
                    "security": [],
                    "responses": {"200": _json_response("Service status", "HealthResponse")},
                }
            },
            "/api/v1/metrics": {
                "get": {
                    "operationId": "listTelecomMetrics",
                    "summary": "List available telecom metrics and their reporting coverage",
                    "parameters": [
                        {
                            "name": "limit",
                            "in": "query",
                            "description": "Maximum metrics to return, from 1 to 500",
                            "schema": {"type": "integer", "minimum": 1, "maximum": 500, "default": 200},
                        }
                    ],
                    "responses": {"200": _json_response("Metric catalogue", "MetricCatalogue")},
                }
            },
            "/api/v1/quality": {
                "get": {
                    "operationId": "getTelecomDataQuality",
                    "summary": "Get aggregated data-quality findings before interpreting results",
                    "responses": {"200": _json_response("Quality summary", "QualitySummary")},
                }
            },
            "/api/v1/analysis/query": {
                "post": {
                    "operationId": "analyzeTelecomData",
                    "summary": "Run deterministic telecom analysis and return graph-ready series with evidence",
                    "description": (
                        "Use for metric lookups, operator comparisons, trends, growth, anomalies, coverage gaps, "
                        "and source-grounded analysis. Never use this operation to authorize network changes."
                    ),
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": ["question"],
                                    "properties": {
                                        "question": {
                                            "type": "string",
                                            "minLength": 1,
                                            "maxLength": 1000,
                                            "description": (
                                                "Specific analytical question including metric, operator, and period where known. "
                                                "Example: Compare MTN and AirtelTigo mobile data subscriptions from 2022 to July 2026."
                                            ),
                                        }
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": _json_response(
                            "Analysis, derived statistics, chart specification, provenance, and governance caveats",
                            "AnalysisResponse",
                        ),
                        "400": {"description": "Invalid request"},
                        "401": {"description": "Missing or invalid API credential"},
                    },
                }
            },
        },
        "components": {
            "securitySchemes": {
                "apiKey": {"type": "apiKey", "in": "header", "name": "X-API-Key"}
            },
            "schemas": _schemas(),
        },
        "security": [{"apiKey": []}],
    }


def _json_response(description: str, schema_name: str) -> dict[str, Any]:
    return {
        "description": description,
        "content": {"application/json": {"schema": {"$ref": f"#/components/schemas/{schema_name}"}}},
    }


def _schemas() -> dict[str, Any]:
    return {
        "HealthResponse": {
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "service": {"type": "string"},
                "authentication_enforced": {"type": "boolean"},
                "residency_verified": {"type": "boolean"},
                "human_authority": {"type": "string"},
            },
        },
        "MetricCatalogue": {
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
                "metrics": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "name": {"type": "string"},
                            "unit": {"type": ["string", "null"]},
                            "definition": {"type": ["string", "null"]},
                            "first_period": {"type": ["string", "null"]},
                            "last_period": {"type": ["string", "null"]},
                            "periods": {"type": "integer"},
                            "operator_count": {"type": "integer"},
                        },
                    },
                },
            },
        },
        "QualitySummary": {
            "type": "object",
            "properties": {
                "total": {"type": "integer"},
                "interpretation": {"type": "string"},
                "findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "severity": {"type": "string"},
                            "issue_code": {"type": "string"},
                            "count": {"type": "integer"},
                        },
                    },
                },
            },
        },
        "AnalysisResponse": {
            "type": "object",
            "properties": {
                "analysis_id": {"type": "string"},
                "answer": {"type": "string"},
                "intent": {"type": "string"},
                "analysis": {
                    "type": "object",
                    "properties": {
                        "metric": {"type": ["string", "null"]},
                        "statistics": {"type": "array", "items": {"type": "object"}},
                        "insights": {"type": "array", "items": {"type": "string"}},
                        "methodology": {"type": "array", "items": {"type": "string"}},
                        "limitations": {"type": "array", "items": {"type": "string"}},
                    },
                },
                "chart": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string"},
                        "title": {"type": "string"},
                        "series": {"type": "array", "items": {"type": "object"}},
                    },
                },
                "evidence": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "operator": {"type": "string"},
                            "period": {"type": "string"},
                            "metric": {"type": "string"},
                            "displayed_value": {"type": "string"},
                            "numeric_value": {"type": ["number", "null"]},
                            "source": {"type": "string"},
                            "quality": {"type": "string"},
                        },
                    },
                },
                "governance": {"type": "object"},
            },
        },
    }
