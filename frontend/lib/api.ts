const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

export async function fetchFailures(page: number = 1, limit: number = 10) {
  const response = await fetch(`${API_BASE_URL}/failures/?page=${page}&limit=${limit}`, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error("Failed to fetch failures");
  }

  return response.json();
}

export async function deleteFailure(testId: string) {
  const response = await fetch(`${API_BASE_URL}/failures/${testId}`, {
    method: "DELETE",
  });

  if (!response.ok) {
    throw new Error("Failed to delete failure");
  }

  return response.json();
}

export async function deleteRecord(endpoint: string, id: string | number) {
  const response = await fetch(`${API_BASE_URL}/${endpoint}/${id}`, {
    method: "DELETE",
  });

  if (!response.ok) {
    throw new Error(`Failed to delete record at ${endpoint}`);
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

export async function fetchHealingActions(page: number = 1, limit: number = 10) {
  const response = await fetch(`${API_BASE_URL}/healing/?page=${page}&limit=${limit}`, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error("Failed to fetch healing actions");
  }

  return response.json();
}

export async function fetchFlakyTests(page: number = 1, limit: number = 10) {
  const response = await fetch(`${API_BASE_URL}/analytics/flaky-tests?page=${page}&limit=${limit}`, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error("Failed to fetch flaky tests");
  }

  return response.json();
}

export async function fetchNotifications(page: number = 1, limit: number = 10) {
  const response = await fetch(`${API_BASE_URL}/notifications/?page=${page}&limit=${limit}`, {
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

export async function fetchRepairHistory(filters: {
  rootCause?: string;
  publishStatus?: string;
  repository?: string;
} = {}) {
  const query = new URLSearchParams();
  if (filters.rootCause) query.set("root_cause", filters.rootCause);
  if (filters.publishStatus) query.set("publish_status", filters.publishStatus);
  if (filters.repository) query.set("repository", filters.repository);
  const suffix = query.size ? `?${query.toString()}` : "";
  const response = await fetch(`${API_BASE_URL}/api/repairs/history${suffix}`, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error("Failed to fetch repair history");
  }

  return response.json();
}
