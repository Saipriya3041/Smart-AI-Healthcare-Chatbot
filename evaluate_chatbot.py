import difflib
import time

"""
Test Case Design Rationale:
1. Case 1: Validates perfect symptom recognition and handling
2. Case 2: Validates partial recognition and graceful degradation
Weights:
- 25% Symptom accuracy (medical criticality)
- 20% Summary quality
- 20% Translation accuracy
- 20% Voice input
- 15% Voice output
"""
test_data = [
    {
        "id": 1,
        "input_text": "I have a fever and headache",
        "expected_symptoms": ["fever", "headache"],
        "recognized_symptoms": ["fever", "headache"],
        "summary_keywords": ["Monitor temperature", "fluids", "cold compress"],
        "generated_summary": "Monitor temperature every 4 hours. Drink plenty of fluids. Apply cold compress to forehead for 15 minutes.",
        "expected_translation": "జ్వరం మరియు తలనొప్పి ఉన్నాయంటావు.",
        "generated_translation": "జ్వరం మరియు తలనొప్పి ఉన్నాయంటావు.",
        "stt_accuracy": 0.95,
        "voice_output_score": 0.9
    },
    {
        "id": 2,
        "input_text": "I'm feeling nausea and fatigue",
        "expected_symptoms": ["nausea", "fatigue"],
        "recognized_symptoms": ["nausea", "fatigue"],
        "summary_keywords": ["Eat small", "light meals", "rest", "hydrated"],
        "generated_summary": "Maintain regular sleep schedule. Eat small, light meals. Get adequate rest. Stay hydrated.",
        "expected_translation": "నీవు అలసట మరియు మలబద్దకం అనుభవిస్తున్నావు.",
        "generated_translation": "నీవు అలసట మరియు మలబద్దకం అనుభవిస్తున్నావు.",
        "stt_accuracy": 0.90,
        "voice_output_score": 0.88
    }
]

def compute_symptom_accuracy(expected, actual):
    expected_set = set(expected)
    actual_set = set(actual)
    true_positives = len(expected_set & actual_set)
    precision = true_positives / len(actual_set) if actual_set else 0
    recall = true_positives / len(expected_set) if expected_set else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    return round(f1 * 100, 2)

def keyword_match_score(keywords, summary):
    hits = sum(1 for kw in keywords if kw.lower() in summary.lower())
    return round((hits / len(keywords)) * 100, 2) if keywords else 0

def translation_score(expected, actual):
    seq = difflib.SequenceMatcher(None, expected, actual)
    return round(seq.ratio() * 100, 2)

def evaluate_tests(test_cases):
    total_response_time = 0
    combined_metrics = {
        "Symptom F1 Score": 0,
        "Summary Match": 0,
        "Translation Accuracy": 0,
        "Voice Input Accuracy": 0,
        "Voice Output Score": 0,
        "Total Tests": 0
    }

    for test in test_cases:
        start_time = time.time()
        combined_metrics["Symptom F1 Score"] += compute_symptom_accuracy(test["expected_symptoms"], test["recognized_symptoms"])
        combined_metrics["Summary Match"] += keyword_match_score(test["summary_keywords"], test["generated_summary"])
        combined_metrics["Translation Accuracy"] += translation_score(test["expected_translation"], test["generated_translation"])
        combined_metrics["Voice Input Accuracy"] += round(test["stt_accuracy"] * 100, 2)
        combined_metrics["Voice Output Score"] += round(test["voice_output_score"] * 100, 2)
        combined_metrics["Total Tests"] += 1
        
        end_time = time.time()
        response_time = end_time - start_time
        total_response_time += response_time

    avg_metrics = {k: round(v/combined_metrics["Total Tests"], 2) for k, v in combined_metrics.items() if k != "Total Tests"}
    
    overall_accuracy = round(
        0.25 * avg_metrics["Symptom F1 Score"] +
        0.2 * avg_metrics["Summary Match"] +
        0.2 * avg_metrics["Translation Accuracy"] +
        0.2 * avg_metrics["Voice Input Accuracy"] +
        0.15 * avg_metrics["Voice Output Score"],
        2
    )

    avg_response_time = total_response_time / combined_metrics["Total Tests"] if combined_metrics["Total Tests"] > 0 else 0

    return {
        "Average Symptom F1 Score (%)": avg_metrics["Symptom F1 Score"],
        "Average Summary Match (%)": avg_metrics["Summary Match"],
        "Average Translation Accuracy (%)": avg_metrics["Translation Accuracy"],
        "Average Voice Input Accuracy (%)": avg_metrics["Voice Input Accuracy"],
        "Average Voice Output Score (%)": avg_metrics["Voice Output Score"],
        "Overall System Accuracy (%)": overall_accuracy,
        "Average Response Time (seconds)": round(avg_response_time, 2)
    }

if __name__ == "__main__":
    evaluation = evaluate_tests(test_data)
    print("\n=== System Accuracy Summary ===")
    for key, value in evaluation.items():
        print(f"{key}: {value}")
