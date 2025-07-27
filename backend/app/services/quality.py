"""
Data quality checking and validation service.
Ensures data integrity, consistency, and completeness.
"""

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Dict, List


class DataQualityChecker:
    """Service for checking data quality and generating quality reports."""

    def __init__(self):
        self.quality_rules = {
            "completeness_threshold": 0.8,  # 80% fields must be complete
            "accuracy_threshold": 0.9,  # 90% data must be accurate
            "consistency_threshold": 0.85,  # 85% data must be consistent
            "duplicate_threshold": 0.05,  # Max 5% duplicates allowed
        }

        self.thresholds = {
            "min_price": 0.01,
            "max_price": 1000000.0,
            "min_name_length": 3,
            "max_name_length": 500,
        }

    def check_completeness(self, data_batch: List[Dict[str, Any]]) -> float:
        """
        Check data completeness score.

        Args:
            data_batch: List of data records

        Returns:
            Completeness score between 0 and 1
        """
        if not data_batch:
            return 0.0

        required_fields = ["name", "price", "availability"]
        total_fields = len(required_fields) * len(data_batch)
        complete_fields = 0

        for record in data_batch:
            for field in required_fields:
                if field in record and record[field] is not None:
                    if isinstance(record[field], str) and record[field].strip():
                        complete_fields += 1
                    elif not isinstance(record[field], str):
                        complete_fields += 1

        return complete_fields / total_fields if total_fields > 0 else 0.0

    def check_accuracy(self, data_batch: List[Dict[str, Any]]) -> float:
        """
        Check data accuracy score.

        Args:
            data_batch: List of data records

        Returns:
            Accuracy score between 0 and 1
        """
        if not data_batch:
            return 0.0

        accurate_records = 0

        for record in data_batch:
            is_accurate = True

            # Check price validity
            if "price" in record and record["price"] is not None:
                try:
                    price = float(record["price"])
                    if (
                        price < self.thresholds["min_price"]
                        or price > self.thresholds["max_price"]
                    ):
                        is_accurate = False
                except (ValueError, TypeError):
                    is_accurate = False

            # Check name validity
            if "name" in record and record["name"]:
                name_length = len(record["name"])
                if (
                    name_length < self.thresholds["min_name_length"]
                    or name_length > self.thresholds["max_name_length"]
                ):
                    is_accurate = False

            # Check currency validity
            if "currency" in record and record["currency"]:
                valid_currencies = {"USD", "EUR", "GBP", "JPY", "CAD", "AUD"}
                if record["currency"] not in valid_currencies:
                    is_accurate = False

            if is_accurate:
                accurate_records += 1

        return accurate_records / len(data_batch)

    def check_consistency(self, data_batch: List[Dict[str, Any]]) -> float:
        """
        Check data consistency score.

        Args:
            data_batch: List of data records

        Returns:
            Consistency score between 0 and 1
        """
        if not data_batch:
            return 0.0

        # Check format consistency
        format_patterns = defaultdict(set)

        for record in data_batch:
            # Currency format consistency
            if "currency" in record and record["currency"]:
                format_patterns["currency"].add(type(record["currency"]).__name__)

            # Price format consistency
            if "price" in record and record["price"] is not None:
                format_patterns["price"].add(type(record["price"]).__name__)

            # Boolean field consistency
            if "availability" in record and record["availability"] is not None:
                format_patterns["availability"].add(
                    type(record["availability"]).__name__
                )

        # Calculate consistency score based on format uniformity
        consistency_scores = []
        for field, types in format_patterns.items():
            # Higher score for fewer type variations
            score = 1.0 / len(types) if types else 1.0
            consistency_scores.append(score)

        return (
            sum(consistency_scores) / len(consistency_scores)
            if consistency_scores
            else 1.0
        )

    def detect_duplicates(
        self, data_batch: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Detect duplicate records in the data batch.

        Args:
            data_batch: List of data records

        Returns:
            List of duplicate records with counts
        """
        # Create signatures for duplicate detection
        signatures = []
        for record in data_batch:
            # Create a signature based on key fields
            sig_parts = []
            if "name" in record and record["name"]:
                sig_parts.append(record["name"].lower().strip())
            if "url" in record and record["url"]:
                sig_parts.append(record["url"])

            signature = "|".join(sig_parts)
            signatures.append(signature)

        # Count occurrences
        signature_counts = Counter(signatures)

        # Find duplicates
        duplicates = []
        processed_signatures = set()

        for i, signature in enumerate(signatures):
            if (
                signature_counts[signature] > 1
                and signature not in processed_signatures
            ):
                # Find all records with this signature
                duplicate_records = [
                    data_batch[j]
                    for j, sig in enumerate(signatures)
                    if sig == signature
                ]

                duplicates.append(
                    {
                        "signature": signature,
                        "count": signature_counts[signature],
                        "records": duplicate_records,
                        "indices": [
                            j for j, sig in enumerate(signatures) if sig == signature
                        ],
                    }
                )

                processed_signatures.add(signature)

        return duplicates

    def check_data_freshness(self, data_batch: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Check data freshness and staleness.

        Args:
            data_batch: List of data records

        Returns:
            Freshness analysis results
        """
        if not data_batch:
            return {"fresh_records": 0, "stale_records": 0, "freshness_score": 0.0}

        current_time = datetime.now()
        fresh_records = 0
        stale_records = 0
        timestamps = []

        for record in data_batch:
            if "scraped_at" in record and record["scraped_at"]:
                try:
                    if isinstance(record["scraped_at"], str):
                        scraped_time = datetime.fromisoformat(
                            record["scraped_at"].replace("Z", "+00:00")
                        )
                    else:
                        scraped_time = record["scraped_at"]

                    age_hours = (current_time - scraped_time).total_seconds() / 3600
                    timestamps.append(age_hours)

                    if age_hours <= 24:  # Fresh if less than 24 hours old
                        fresh_records += 1
                    else:
                        stale_records += 1

                except (ValueError, TypeError):
                    stale_records += 1
            else:
                stale_records += 1

        total_records = len(data_batch)
        freshness_score = fresh_records / total_records if total_records > 0 else 0.0

        return {
            "fresh_records": fresh_records,
            "stale_records": stale_records,
            "total_records": total_records,
            "freshness_score": freshness_score,
            "average_age_hours": sum(timestamps) / len(timestamps)
            if timestamps
            else None,
            "oldest_record_hours": max(timestamps) if timestamps else None,
        }

    def analyze_price_distribution(
        self, data_batch: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Analyze price distribution for anomaly detection.

        Args:
            data_batch: List of data records

        Returns:
            Price distribution analysis
        """
        prices = []

        for record in data_batch:
            if "price" in record and record["price"] is not None:
                try:
                    price = float(record["price"])
                    if price > 0:
                        prices.append(price)
                except (ValueError, TypeError):
                    continue

        if not prices:
            return {"error": "No valid prices found"}

        prices.sort()
        n = len(prices)

        # Calculate statistics
        min_price = min(prices)
        max_price = max(prices)
        avg_price = sum(prices) / n

        # Calculate median
        if n % 2 == 0:
            median_price = (prices[n // 2 - 1] + prices[n // 2]) / 2
        else:
            median_price = prices[n // 2]

        # Calculate quartiles
        q1_idx = n // 4
        q3_idx = 3 * n // 4
        q1 = prices[q1_idx]
        q3 = prices[q3_idx]

        # Detect outliers using IQR method
        iqr = q3 - q1
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr

        outliers = [p for p in prices if p < lower_bound or p > upper_bound]

        return {
            "total_prices": n,
            "min_price": min_price,
            "max_price": max_price,
            "average_price": avg_price,
            "median_price": median_price,
            "q1": q1,
            "q3": q3,
            "iqr": iqr,
            "outliers_count": len(outliers),
            "outliers": outliers[:10],  # Show first 10 outliers
            "outlier_percentage": len(outliers) / n * 100,
        }

    def generate_quality_report(
        self, data_batch: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Generate comprehensive data quality report.

        Args:
            data_batch: List of data records

        Returns:
            Comprehensive quality report
        """
        if not data_batch:
            return {
                "error": "No data provided for quality analysis",
                "total_records": 0,
            }

        # Run all quality checks
        completeness_score = self.check_completeness(data_batch)
        accuracy_score = self.check_accuracy(data_batch)
        consistency_score = self.check_consistency(data_batch)
        duplicates = self.detect_duplicates(data_batch)
        freshness_analysis = self.check_data_freshness(data_batch)
        price_analysis = self.analyze_price_distribution(data_batch)

        # Calculate overall quality score
        overall_score = (completeness_score + accuracy_score + consistency_score) / 3

        # Generate issues list
        issues = []

        if completeness_score < self.quality_rules["completeness_threshold"]:
            issues.append(
                f"Low completeness: {completeness_score:.2%} (threshold: {self.quality_rules['completeness_threshold']:.2%})"
            )

        if accuracy_score < self.quality_rules["accuracy_threshold"]:
            issues.append(
                f"Low accuracy: {accuracy_score:.2%} (threshold: {self.quality_rules['accuracy_threshold']:.2%})"
            )

        if consistency_score < self.quality_rules["consistency_threshold"]:
            issues.append(
                f"Low consistency: {consistency_score:.2%} (threshold: {self.quality_rules['consistency_threshold']:.2%})"
            )

        duplicate_percentage = len(duplicates) / len(data_batch) if data_batch else 0
        if duplicate_percentage > self.quality_rules["duplicate_threshold"]:
            issues.append(
                f"High duplicate rate: {duplicate_percentage:.2%} (threshold: {self.quality_rules['duplicate_threshold']:.2%})"
            )

        return {
            "total_records": len(data_batch),
            "completeness_score": completeness_score,
            "accuracy_score": accuracy_score,
            "consistency_score": consistency_score,
            "overall_quality_score": overall_score,
            "duplicate_count": len(duplicates),
            "duplicate_percentage": duplicate_percentage,
            "freshness_analysis": freshness_analysis,
            "price_analysis": price_analysis,
            "issues": issues,
            "quality_grade": self._calculate_quality_grade(overall_score),
            "recommendations": self._generate_recommendations(
                completeness_score, accuracy_score, consistency_score, duplicates
            ),
            "generated_at": datetime.now().isoformat(),
        }

    def _calculate_quality_grade(self, score: float) -> str:
        """Calculate quality grade based on score."""
        if score >= 0.95:
            return "A+"
        elif score >= 0.90:
            return "A"
        elif score >= 0.85:
            return "B+"
        elif score >= 0.80:
            return "B"
        elif score >= 0.75:
            return "C+"
        elif score >= 0.70:
            return "C"
        elif score >= 0.60:
            return "D"
        else:
            return "F"

    def _generate_recommendations(
        self,
        completeness: float,
        accuracy: float,
        consistency: float,
        duplicates: List[Dict[str, Any]],
    ) -> List[str]:
        """Generate improvement recommendations."""
        recommendations = []

        if completeness < 0.8:
            recommendations.append(
                "Improve data collection to ensure all required fields are populated"
            )

        if accuracy < 0.9:
            recommendations.append(
                "Review data validation rules and improve parsing accuracy"
            )

        if consistency < 0.85:
            recommendations.append(
                "Standardize data formats and implement consistent validation"
            )

        if len(duplicates) > 0:
            recommendations.append(
                "Implement deduplication logic to remove duplicate records"
            )

        if not recommendations:
            recommendations.append(
                "Data quality is good. Continue monitoring for consistency"
            )

        return recommendations
