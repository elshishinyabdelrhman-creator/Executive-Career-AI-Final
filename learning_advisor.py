from __future__ import annotations

import re

TOOLS = [
    "SQL", "Google Analytics 4", "Looker Studio", "Power BI", "Tableau", "Metabase",
    "Excel", "Shopify", "Google Merchant Center", "Salesforce", "HubSpot", "Snowflake", "dbt",
]

KEYWORDS = [
    "Sales Strategy", "Commercial Planning", "Revenue Growth", "Customer Acquisition",
    "Customer Retention", "Sales Forecasting", "Supplier Relationships", "Product Mix",
    "Assortment Strategy", "Conversion Optimization", "Average Order Value", "Basket Size",
    "Repeat Purchase", "Customer Experience", "Market Analysis", "Cross-Functional Collaboration",
    "Campaign Management", "Business Development", "Pricing Strategy", "Data-Driven Decision Making",
]

COURSES = [
    "Commercial Excellence — Coursera / LinkedIn Learning",
    "Retail Pricing Strategy — Coursera / LinkedIn Learning",
    "Sales Forecasting — Coursera / LinkedIn Learning",
    "Strategic Negotiation — Coursera / Yale",
    "AI for Business Leaders — Microsoft Learn / Coursera",
    "Financial Modeling and Forecasting — Coursera",
]

BOOKS = [
    "Good Strategy/Bad Strategy — Richard Rumelt",
    "Influence — Robert Cialdini",
    "Measure What Matters — John Doerr",
    "Never Split the Difference — Chris Voss",
]


def _contains(text: str, term: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", " ", text.lower())
    target = re.sub(r"[^a-z0-9]+", " ", term.lower()).strip()
    return bool(target and target in normalized)


def build_learning_plan(job_description: str, role: str, industry: str, master_resume: str) -> dict:
    combined = f"{role} {industry} {job_description}"
    evidenced_tools = [tool for tool in TOOLS if _contains(master_resume, tool)]
    tools_to_learn = [
        tool for tool in TOOLS
        if _contains(combined, tool) and tool not in evidenced_tools
    ]
    if not tools_to_learn:
        tools_to_learn = [tool for tool in TOOLS if tool not in evidenced_tools][:8]

    industry_keywords = [term for term in KEYWORDS if _contains(combined, term)]
    if len(industry_keywords) < 10:
        industry_keywords = KEYWORDS[:18]

    return {
        "evidenced_tools": evidenced_tools,
        "tools_to_learn": tools_to_learn[:10],
        "recommended_courses": COURSES,
        "recommended_books": BOOKS,
        "industry_keywords": industry_keywords[:20],
    }
