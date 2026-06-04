
SCHEMA = {
    "openapi": "3.0.0",
    "info": {
        "title": "BeautiCare AI API",
        "version": "1.0.0",
        "description": "API for BeautiCare AI — Atharva haircare chatbot powered by Gemini.",
        "contact": {
            "name": "BeautiCare Support",
        },
    },
    "servers": [
        {"url": "http://127.0.0.1:8000", "description": "Local Development"},
    ],
    "tags": [
        {"name": "Sessions",  "description": "Chat session management"},
        {"name": "Messages",  "description": "Sending and reading messages"},
        {"name": "Products",  "description": "Product search"},
    ],
    "paths": {
        "/api/sessions/new/": {
            "post": {
                "tags": ["Sessions"],
                "summary": "Create a new chat session",
                "description": "Creates a new consultation session and returns its ID.",
                "responses": {
                    "200": {
                        "description": "Session created successfully",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "session_id":    {"type": "string", "example": "161b16f2-3127-4975-8a3d-74bc19dd142a"},
                                        "redirect_url":  {"type": "string", "example": "/chat/161b16f2-3127-4975-8a3d-74bc19dd142a/"},
                                    },
                                }
                            }
                        },
                    }
                },
            }
        },
        "/api/sessions/{session_id}/send/": {
            "post": {
                "tags": ["Messages"],
                "summary": "Send a message and get AI reply",
                "description": (
                    "Sends a user message to BeautiCare AI. "
                    "Gemini tool calls fetch products from DB automatically. "
                    "Returns AI reply text and optional product cards."
                ),
                "parameters": [
                    {
                        "name": "session_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                        "example": "161b16f2-3127-4975-8a3d-74bc19dd142a",
                    }
                ],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["message"],
                                "properties": {
                                    "message": {
                                        "type": "string",
                                        "example": "my hair is falling a lot",
                                        "description": "User's chat message",
                                    }
                                },
                            },
                            "examples": {
                                "greeting": {
                                    "summary": "Simple greeting",
                                    "value": {"message": "hi"},
                                },
                                "hair_problem": {
                                    "summary": "Hair concern",
                                    "value": {"message": "my hair is falling a lot"},
                                },
                                "show_products": {
                                    "summary": "Show all products",
                                    "value": {"message": "show all products"},
                                },
                                "price_query": {
                                    "summary": "Price query",
                                    "value": {"message": "what is price of argan oil hair serum"},
                                },
                            },
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "AI response with optional product cards",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "reply": {
                                            "type": "string",
                                            "description": "AI text response shown as chat bubble",
                                            "example": "Hair fall is often caused by weak bonds...",
                                        },
                                        "message_id": {
                                            "type": "string",
                                            "description": "Saved message ID",
                                            "example": "42",
                                        },
                                        "session_id": {
                                            "type": "string",
                                            "example": "161b16f2-3127-4975-8a3d-74bc19dd142a",
                                        },
                                        "session_title": {
                                            "type": "string",
                                            "description": "Auto-generated session title",
                                            "example": "My Hair Is Falling",
                                        },
                                        "session_category": {
                                            "type": "string",
                                            "enum": ["hair", "skin", "makeup", "wellness", "general"],
                                            "example": "hair",
                                        },
                                        "is_first_message": {
                                            "type": "boolean",
                                            "description": "True if this is the first message in session",
                                            "example": False,
                                        },
                                        "products": {
                                            "type": "array",
                                            "description": "Product cards — empty if no products matched",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "name":        {"type": "string", "example": "Argan Oil Hair Serum"},
                                                    "brand":       {"type": "string", "example": "Atharva"},
                                                    "price":       {"type": "string", "example": "850"},
                                                    "rating":      {"type": "string", "example": "4.6"},
                                                    "description": {"type": "string"},
                                                    "how_to_use":  {"type": "string"},
                                                    "image":       {"type": "string", "example": "http://127.0.0.1:8000/media/products/serum.jpg"},
                                                },
                                            },
                                        },
                                        "ai_analysis": {
                                            "type": "object",
                                            "description": "Detected hair problem metadata",
                                            "properties": {
                                                "problem_type":          {"type": "string", "example": "hair_fall"},
                                                "severity":              {"type": "string", "example": "moderate"},
                                                "summary":               {"type": "string", "example": "hair fall"},
                                                "is_competitor_brand":   {"type": "boolean", "example": False},
                                                "competitor_brand_name": {"type": "string", "example": ""},
                                            },
                                        },
                                    },
                                },
                                "examples": {
                                    "greeting_response": {
                                        "summary": "Response to hi",
                                        "value": {
                                            "reply": "Hi! I'm BeautiCare AI — your Atharva hair advisor. What hair or scalp concern can I help with?",
                                            "products": [],
                                            "session_category": "general",
                                            "is_first_message": True,
                                        },
                                    },
                                    "product_response": {
                                        "summary": "Response with product cards",
                                        "value": {
                                            "reply": "Hair fall is often a bond-strength issue. The Silk Bond Treatment rebuilds internal bonds stopping breakage.",
                                            "products": [
                                                {
                                                    "name": "Silk Bond Treatment",
                                                    "brand": "Atharva",
                                                    "price": "999",
                                                    "rating": "4.7",
                                                    "image": "http://127.0.0.1:8000/media/products/silkbond.jpg",
                                                }
                                            ],
                                            "session_category": "hair",
                                            "ai_analysis": {
                                                "problem_type": "hair_fall",
                                                "severity": "moderate",
                                            },
                                        },
                                    },
                                },
                            }
                        },
                    },
                    "400": {
                        "description": "Bad request — empty or invalid message",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "error": {"type": "string", "example": "Message cannot be empty"}
                                    },
                                }
                            }
                        },
                    },
                    "403": {
                        "description": "Forbidden — session belongs to another user",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "error": {"type": "string", "example": "Forbidden"}
                                    },
                                }
                            }
                        },
                    },
                    "503": {
                        "description": "AI service unavailable",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "error": {"type": "string", "example": "AI service error: Gemini timed out"}
                                    },
                                }
                            }
                        },
                    },
                },
            }
        },
        "/api/sessions/{session_id}/delete/": {
            "post": {
                "tags": ["Sessions"],
                "summary": "Soft delete a session",
                "description": "Marks the session as inactive (not permanently deleted).",
                "parameters": [
                    {
                        "name": "session_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Session deactivated",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "success": {"type": "boolean", "example": True}
                                    },
                                }
                            }
                        },
                    }
                },
            }
        },
        "/api/sessions/{session_id}/rename/": {
            "post": {
                "tags": ["Sessions"],
                "summary": "Rename a session",
                "parameters": [
                    {
                        "name": "session_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["title"],
                                "properties": {
                                    "title": {"type": "string", "example": "My Hair Fall Session"}
                                },
                            }
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Session renamed",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "success": {"type": "boolean", "example": True},
                                        "title":   {"type": "string", "example": "My Hair Fall Session"},
                                    },
                                }
                            }
                        },
                    }
                },
            }
        },
        "/api/sessions/": {
            "get": {
                "tags": ["Sessions"],
                "summary": "List all sessions grouped by time",
                "responses": {
                    "200": {
                        "description": "Grouped sessions",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "groups": {
                                            "type": "object",
                                            "description": "Sessions grouped by Today / Yesterday / This week / Older",
                                            "example": {
                                                "Today": [
                                                    {
                                                        "id": "161b16f2-...",
                                                        "title": "Hair Fall Help",
                                                        "category": "hair",
                                                        "preview": "Hair fall is often caused by...",
                                                        "updated_at": "2026-05-22T14:00:00Z",
                                                    }
                                                ]
                                            },
                                        }
                                    },
                                }
                            }
                        },
                    }
                },
            }
        },
        "/api/sessions/{session_id}/messages/": {
            "get": {
                "tags": ["Messages"],
                "summary": "Get all messages in a session",
                "parameters": [
                    {
                        "name": "session_id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
                "responses": {
                    "200": {
                        "description": "List of messages",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "messages": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "role":     {"type": "string", "enum": ["user", "assistant"]},
                                                    "content":  {"type": "string"},
                                                    "products": {"type": "array", "items": {"type": "object"}},
                                                },
                                            },
                                        }
                                    },
                                }
                            }
                        },
                    }
                },
            }
        },
        "/api/products/search/": {
            "get": {
                "tags": ["Products"],
                "summary": "Search products by query",
                "parameters": [
                    {
                        "name": "q",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "string"},
                        "example": "hair fall",
                        "description": "Search query — e.g. 'dandruff', 'frizzy hair', 'serum'",
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Matching products",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "products": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "name":         {"type": "string"},
                                                    "brand":        {"type": "string"},
                                                    "price":        {"type": "string"},
                                                    "rating":       {"type": "string"},
                                                    "description":  {"type": "string"},
                                                    "how_to_use":   {"type": "string"},
                                                    "key_benefits": {"type": "array", "items": {"type": "string"}},
                                                    "avoid_if":     {"type": "string"},
                                                    "category":     {"type": "string"},
                                                    "image":        {"type": "string"},
                                                },
                                            },
                                        }
                                    },
                                }
                            }
                        },
                    }
                },
            }
        },
    },
    "components": {
        "schemas": {
            "Product": {
                "type": "object",
                "properties": {
                    "name":        {"type": "string", "example": "Argan Oil Hair Serum"},
                    "brand":       {"type": "string", "example": "Atharva"},
                    "price":       {"type": "string", "example": "850"},
                    "rating":      {"type": "string", "example": "4.6"},
                    "description": {"type": "string"},
                    "how_to_use":  {"type": "string"},
                    "image":       {"type": "string"},
                },
            },
            "Error": {
                "type": "object",
                "properties": {
                    "error": {"type": "string"}
                },
            },
        }
    },
}