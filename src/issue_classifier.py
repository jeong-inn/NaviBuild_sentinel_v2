"""
NaviBuild-Sentinel v2 — Module 3-1: TF-IDF Issue Classifier

로그 메시지를 TF-IDF 벡터화하여 이슈를 자동 분류.
코사인 유사도를 통해 기존 이슈와의 관계를 판단:
  - KNOWN (≥0.75): 기존 이슈에 매핑
  - SIMILAR (0.45~0.75): 유사 이슈 후보
  - NEW (<0.45): 신규 이슈

"""

import re
import json
from pathlib import Path
from collections import defaultdict

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


# ──────────────────────────────────────────────
# Issue Category Definitions
# ──────────────────────────────────────────────

ISSUE_CATEGORIES = {
    "CRASH": {
        "description": "프로세스 비정상 종료, 워치독 트리거",
        "seed_messages": [
            "engine crashed context lost",
            "fatal exception null pointer dereference",
            "process terminated unexpectedly SIGSEGV",
            "watchdog triggered unresponsive",
            "framework crash deadlock detected",
        ]
    },
    "PERFORMANCE": {
        "description": "타임아웃, 지연, 프레임 드랍",
        "seed_messages": [
            "calculation timeout exceeded threshold",
            "deadline exceeded path engine",
            "rendering latency spike frame",
            "search response time degraded",
            "decompression stalled decode blocked",
        ]
    },
    "DATA_ERROR": {
        "description": "지도 데이터 무결성 오류",
        "seed_messages": [
            "data integrity check failed CRC mismatch",
            "database index corrupted overflow",
            "road network topology error disconnected",
            "search index inconsistency duplicate",
        ]
    },
    "ROUTE_ERROR": {
        "description": "경로 계산/안내 오류",
        "seed_messages": [
            "invalid route generated U-turn highway",
            "guidance mismatch announced exit path",
            "alternative route calculation failed",
            "ETA calculation error diverges historical",
        ]
    },
    "CONNECTIVITY": {
        "description": "텔레매틱스/네트워크 오류",
        "seed_messages": [
            "telematics connection lost broker unreachable",
            "traffic data sync failed HTTP server",
            "OTA manifest download interrupted reset",
        ]
    },
    "OTA_ISSUE": {
        "description": "OTA 업데이트 관련 오류",
        "seed_messages": [
            "OTA update verification failed signature mismatch",
            "post-update health check failed startup timeout",
            "OTA rollback triggered version incompatibility",
        ]
    },
    "UNKNOWN": {
        "description": "분류 불가 패턴",
        "seed_messages": [
            "unrecognized message type module",
            "unexpected state transition lifecycle",
            "unknown format version header",
            "unhandled event type state machine",
            "undefined behavior flag optimizer",
        ]
    },
}


class IssueClassifier:
    """
    TF-IDF 기반 이슈 분류기.
    
    동작 방식:
    1. seed_messages로 카테고리별 TF-IDF 벡터 사전 구축
    2. 새 로그 메시지 → TF-IDF 벡터 변환
    3. 전체 카테고리 seed와 코사인 유사도 계산
    4. 가장 높은 유사도의 카테고리로 분류
    
    추가: 이슈 클러스터링 (같은 root cause 그룹핑)
    - 분류된 이슈들 간의 pair-wise 유사도 계산
    - 유사도 > CLUSTER_THRESHOLD인 이슈들을 같은 클러스터로 묶음
    """

    KNOWN_THRESHOLD = 0.75     # 기존 이슈 확정
    SIMILAR_THRESHOLD = 0.45   # 유사 이슈 후보
    CLUSTER_THRESHOLD = 0.60   # 클러스터링 임계치

    def __init__(self):
        self.vectorizer = TfidfVectorizer(
            stop_words="english",
            max_features=500,
            ngram_range=(1, 2),    # unigram + bigram
            sublinear_tf=True,     # log-normalized TF
        )
        self._build_seed_corpus()
        self.issue_db = []         # 누적 이슈 DB
        self.cluster_counter = 0   # 클러스터 ID 카운터

    def _preprocess(self, text):
        """Normalize log message for TF-IDF."""
        text = text.lower()
        # Remove hex addresses and numbers but keep meaningful tokens
        text = re.sub(r'0x[0-9a-f]+', 'HEX_ADDR', text)
        text = re.sub(r'\b\d{4,}\b', 'NUM', text)  # long numbers
        text = re.sub(r'[_/\\.]', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _build_seed_corpus(self):
        """Build TF-IDF vectors from seed messages."""
        self.seed_labels = []
        self.seed_messages = []
        for category, info in ISSUE_CATEGORIES.items():
            for msg in info["seed_messages"]:
                self.seed_labels.append(category)
                self.seed_messages.append(self._preprocess(msg))

        # Fit vectorizer on seed corpus
        self.seed_vectors = self.vectorizer.fit_transform(self.seed_messages)

    def classify_message(self, message):
        """
        Classify a single log message.
        
        Returns:
            dict with:
                - category: predicted category
                - confidence: max cosine similarity score
                - match_type: KNOWN / SIMILAR / NEW
                - top_matches: top 3 similar categories with scores
                - explanation: 분류 근거 (TF-IDF 상위 키워드)
        """
        processed = self._preprocess(message)
        msg_vector = self.vectorizer.transform([processed])

        # Compute similarity against all seed messages
        similarities = cosine_similarity(msg_vector, self.seed_vectors)[0]

        # Aggregate by category (max similarity per category)
        category_scores = defaultdict(float)
        for idx, sim in enumerate(similarities):
            cat = self.seed_labels[idx]
            category_scores[cat] = max(category_scores[cat], sim)

        # Sort by score
        ranked = sorted(category_scores.items(), key=lambda x: x[1], reverse=True)
        best_cat, best_score = ranked[0]

        # Determine match type
        if best_score >= self.KNOWN_THRESHOLD:
            match_type = "KNOWN"
        elif best_score >= self.SIMILAR_THRESHOLD:
            match_type = "SIMILAR"
        else:
            match_type = "NEW"

        # Extract explanation (top TF-IDF features for this message)
        feature_names = self.vectorizer.get_feature_names_out()
        msg_tfidf = msg_vector.toarray()[0]
        top_feature_indices = msg_tfidf.argsort()[-5:][::-1]
        explanation_features = [
            (feature_names[i], round(msg_tfidf[i], 3))
            for i in top_feature_indices if msg_tfidf[i] > 0
        ]

        return {
            "category": best_cat,
            "confidence": round(best_score, 4),
            "match_type": match_type,
            "top_matches": [
                {"category": cat, "score": round(sc, 4)}
                for cat, sc in ranked[:3]
            ],
            "explanation": explanation_features,
        }

    def classify_events(self, error_events):
        """
        Classify a list of error events.
        
        Args:
            error_events: list of dicts from DLTLogParser.get_error_events()
        
        Returns:
            list of classified issue dicts
        """
        classified = []
        for event in error_events:
            result = self.classify_message(event["message"])

            issue = {
                "event_id": event["id"],
                "timestamp": event["timestamp"],
                "build_version": event["build_version"],
                "context_id": event["context_id"],
                "log_level": event["log_level"],
                "message": event["message"],
                "vehicle_variant": event["vehicle_variant"],
                "region": event["region"],
                "original_issue_type": event.get("issue_type"),
                "error_code": event.get("error_code"),
                # Classification results
                "classified_category": result["category"],
                "confidence": result["confidence"],
                "match_type": result["match_type"],
                "top_matches": result["top_matches"],
                "explanation": result["explanation"],
            }
            classified.append(issue)

        # Perform clustering on classified issues
        classified = self._cluster_issues(classified)

        return classified

    def _cluster_issues(self, issues):
        """
        Cluster similar issues by computing pair-wise similarity.
        Issues in the same cluster likely share the same root cause.
        """
        if not issues:
            return issues

        # Vectorize all issue messages
        messages = [self._preprocess(i["message"]) for i in issues]
        vectors = self.vectorizer.transform(messages)
        sim_matrix = cosine_similarity(vectors)

        # Union-Find clustering
        n = len(issues)
        parent = list(range(n))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for i in range(n):
            for j in range(i + 1, n):
                if sim_matrix[i][j] >= self.CLUSTER_THRESHOLD:
                    union(i, j)

        # Assign cluster IDs
        cluster_map = {}
        for i in range(n):
            root = find(i)
            if root not in cluster_map:
                self.cluster_counter += 1
                cluster_map[root] = f"CLU-{self.cluster_counter:04d}"
            issues[i]["cluster_id"] = cluster_map[root]

        # Add cluster size info
        cluster_sizes = defaultdict(int)
        for issue in issues:
            cluster_sizes[issue["cluster_id"]] += 1
        for issue in issues:
            issue["cluster_size"] = cluster_sizes[issue["cluster_id"]]

        return issues

    def get_classification_summary(self, classified_issues):
        """Generate summary statistics for classified issues."""
        summary = {
            "total_issues": len(classified_issues),
            "by_category": defaultdict(int),
            "by_match_type": defaultdict(int),
            "clusters": defaultdict(list),
            "avg_confidence": 0.0,
        }

        total_conf = 0.0
        for issue in classified_issues:
            summary["by_category"][issue["classified_category"]] += 1
            summary["by_match_type"][issue["match_type"]] += 1
            summary["clusters"][issue["cluster_id"]].append(
                issue["classified_category"]
            )
            total_conf += issue["confidence"]

        if classified_issues:
            summary["avg_confidence"] = round(
                total_conf / len(classified_issues), 4
            )

        # Convert defaultdicts for serialization
        summary["by_category"] = dict(summary["by_category"])
        summary["by_match_type"] = dict(summary["by_match_type"])
        summary["cluster_count"] = len(summary["clusters"])
        summary["clusters"] = {
            k: {"count": len(v), "categories": list(set(v))}
            for k, v in summary["clusters"].items()
        }

        return summary


if __name__ == "__main__":
    # Quick test
    classifier = IssueClassifier()

    test_messages = [
        "Map rendering engine crashed: OpenGL context lost",
        "Route calculation timeout: path_engine exceeded 3000ms threshold",
        "Path calculation deadline exceeded: 4200ms for route segment",
        "Map data integrity check failed: CRC mismatch on tile",
        "Unrecognized IPC message type 0xAF from module nav_aux",
    ]

    print("NaviBuild-Sentinel v2 — Issue Classifier Test")
    print("=" * 60)
    for msg in test_messages:
        result = classifier.classify_message(msg)
        print(f"\nMessage: {msg[:60]}...")
        print(f"  → Category: {result['category']} "
              f"(confidence: {result['confidence']}, "
              f"type: {result['match_type']})")
        print(f"  → Top keywords: {result['explanation'][:3]}")