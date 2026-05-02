const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

export async function fetchFailures() {
  const response = await fetch(`${API_BASE_URL}/failures/`, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error("Failed to fetch failures");
  }

  return response.json();
}

export async function fetchFailureById(testId: string) {
  const response = await fetch(`${API_BASE_URL}/failures/${testId}`, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error("Failed to fetch failure details");
  }

  return response.json();
}

export async function fetchHealingActions() {
  const response = await fetch(`${API_BASE_URL}/healing/`, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error("Failed to fetch healing actions");
  }

  return response.json();
}

export async function fetchFlakyTests() {
  const response = await fetch(`${API_BASE_URL}/analytics/flaky-tests`, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error("Failed to fetch flaky tests");
  }

  return response.json();
}

export async function fetchNotifications() {
  const response = await fetch(`${API_BASE_URL}/notifications/`, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error("Failed to fetch notifications");
  }

  return response.json();
}

export async function fetchDashboardSummary() {
  const response = await fetch(`${API_BASE_URL}/dashboard/summary`, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error("Failed to fetch dashboard summary");
  }

  return response.json();
}