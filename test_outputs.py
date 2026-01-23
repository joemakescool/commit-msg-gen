"""
Test Script - See what commit messages look like.

Usage:
  python test_outputs.py              # test all scenarios
  python test_outputs.py -s small     # test one scenario
  python test_outputs.py -m mistral:7b  # use different model
"""

import sys
sys.path.insert(0, 'src')

from diff_processor import ProcessedDiff
from prompt_builder import PromptBuilder, PromptConfig
from llm_client import get_client, LLMError

# Sample scenarios to test
SCENARIOS = {
    "small": {
        "name": "Small Fix (2 files)",
        "file_count": 2,
        "summary": """FILES CHANGED:
src/utils/validator.py | +15 -3 | Modified
src/utils/__init__.py  | +1 -0  | Modified

CHANGES:
- validator.py: Added null check for email field
- __init__.py: Exported new validate_email function""",
        "diff": """diff --git a/src/utils/validator.py b/src/utils/validator.py
--- a/src/utils/validator.py
+++ b/src/utils/validator.py
@@ -12,6 +12,9 @@ def validate_user(user):
+def validate_email(email):
+    if email is None:
+        return False
+    return '@' in email and '.' in email"""
    },
    
    "medium": {
        "name": "Medium Feature (6 files)",
        "file_count": 6,
        "summary": """FILES CHANGED:
src/api/auth_controller.py    | +85 -12 | Modified
src/services/auth_service.py  | +120 -0 | Added
src/models/user.py            | +25 -5  | Modified
src/middleware/jwt.py         | +45 -0  | Added
tests/test_auth.py            | +90 -0  | Added
config/auth.yaml              | +15 -0  | Added

CHANGES:
- auth_controller.py: New login/logout endpoints
- auth_service.py: JWT token generation and validation
- user.py: Added password_hash and last_login fields
- jwt.py: Middleware for protected routes
- test_auth.py: Unit tests for auth flow
- auth.yaml: JWT secret and expiration config""",
        "diff": """diff --git a/src/api/auth_controller.py b/src/api/auth_controller.py
+@app.post("/login")
+def login(credentials: LoginRequest):
+    user = auth_service.authenticate(credentials.email, credentials.password)
+    if not user:
+        raise HTTPException(401, "Invalid credentials")
+    token = auth_service.generate_token(user)
+    return {"token": token, "user": user.to_dict()}
+
+@app.post("/logout")
+def logout(token: str = Depends(get_current_token)):
+    auth_service.invalidate_token(token)
+    return {"message": "Logged out"}"""
    },
    
    "large": {
        "name": "Large Refactor (18 files)",
        "file_count": 18,
        "summary": """FILES CHANGED:
src/api/predictions_controller.py  | +45 -120 | Modified
src/api/teams_controller.py        | +30 -85  | Modified
src/api/games_controller.py        | +25 -70  | Modified
src/services/prediction_service.py | +180 -0  | Added
src/services/team_service.py       | +95 -0   | Added
src/services/game_service.py       | +85 -0   | Added
src/repositories/prediction_repo.py| +120 -0  | Added
src/repositories/team_repo.py      | +80 -0   | Added
src/repositories/game_repo.py      | +75 -0   | Added
src/models/prediction.py           | +45 -15  | Modified
src/models/team.py                 | +30 -10  | Modified
src/models/game.py                 | +35 -12  | Modified
src/utils/query_builder.py         | +150 -0  | Added
src/utils/cache.py                 | +60 -0   | Added
tests/test_prediction_service.py   | +200 -0  | Added
tests/test_team_service.py         | +120 -0  | Added
tests/test_repositories.py         | +180 -0  | Added
config/database.yaml               | +25 -5   | Modified

CHANGES:
- Extracted business logic from controllers into dedicated service classes
- Created repository layer for database operations
- Added query builder utility for complex Polars DataFrame operations
- Implemented caching layer for frequently accessed data
- Controllers now only handle HTTP concerns
- Added comprehensive test coverage for new service layer
- Updated models with new relationships and validation""",
        "diff": """diff --git a/src/services/prediction_service.py b/src/services/prediction_service.py
+class PredictionService:
+    def __init__(self, repo: PredictionRepository, cache: Cache):
+        self.repo = repo
+        self.cache = cache
+    
+    def get_predictions(self, week: int, season: int) -> list[Prediction]:
+        cache_key = f"predictions:{season}:{week}"
+        if cached := self.cache.get(cache_key):
+            return cached
+        predictions = self.repo.find_by_week(week, season)
+        self.cache.set(cache_key, predictions, ttl=3600)
+        return predictions
+    
+    def calculate_upset_probability(self, game: Game) -> float:
+        # Complex logic extracted from controller
+        home_strength = self.team_service.get_strength(game.home_team)
+        away_strength = self.team_service.get_strength(game.away_team)
+        return self._calculate_probability(home_strength, away_strength)"""
    }
}


def create_mock_diff(scenario: dict) -> ProcessedDiff:
    """Create a ProcessedDiff object from scenario data."""
    return ProcessedDiff(
        summary=scenario["summary"],
        detailed_diff=scenario["diff"],
        total_files=scenario["file_count"],
        filtered_files=0,
        truncated=False
    )


def run_test(scenario_key: str, provider: str = "ollama", model: str = None):
    """Run a single test scenario."""
    scenario = SCENARIOS[scenario_key]
    print(f"\n{'='*60}")
    print(f"SCENARIO: {scenario['name']}")
    print(f"{'='*60}\n")
    
    # Create mock diff
    diff = create_mock_diff(scenario)
    
    # Build prompt
    config = PromptConfig(
        file_count=scenario["file_count"]
    )
    builder = PromptBuilder()
    prompt = builder.build(diff, config)
    
    # Show what we're sending
    print(f"Files: {scenario['file_count']}")
    print(f"Prompt size: ~{len(prompt)//4} tokens\n")
    
    # Call LLM
    try:
        client = get_client(provider=provider, model=model)
        print(f"Using: {client.name}")
        print("Generating...\n")
        response = client.generate(prompt)
        
        print("-" * 40)
        print("OUTPUT:")
        print("-" * 40)
        print(response.content)
        print("-" * 40)
        
        # Count bullets
        bullets = response.content.count("\n-")
        print(f"\nBullet count: {bullets}")
        
    except LLMError as e:
        print(f"Error: {e}")


def run_all_tests(provider: str = "ollama", model: str = None):
    """Run all test scenarios."""
    print("\n" + "="*60)
    print("COMMIT MESSAGE GENERATOR - OUTPUT TESTS")
    print("="*60)
    
    for key in ["small", "medium", "large"]:
        run_test(key, provider, model)
        print("\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Test commit message output")
    parser.add_argument("-s", "--scenario", choices=["small", "medium", "large", "all"], default="all")
    parser.add_argument("-p", "--provider", default="ollama")
    parser.add_argument("-m", "--model", default=None)
    args = parser.parse_args()
    
    if args.scenario == "all":
        run_all_tests(args.provider, args.model)
    else:
        run_test(args.scenario, args.provider, args.model)
