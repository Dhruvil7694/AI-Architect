/* eslint-disable @typescript-eslint/no-explicit-any */
const DEFAULT_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type HttpMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export interface HttpClientConfig {
  baseUrl?: string;
}

export interface HttpErrorShape {
  status: number;
  code?: string;
  message: string;
  details?: unknown;
}

export class HttpError extends Error implements HttpErrorShape {
  status: number;
  code?: string | undefined;
  details?: unknown;

  constructor({ status, code, message, details }: HttpErrorShape) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

const config: HttpClientConfig = {
  baseUrl: DEFAULT_BASE_URL,
};

export async function httpRequest<TResponse, TBody = unknown>(
  path: string,
  options: {
    method?: HttpMethod;
    body?: TBody;
    searchParams?: Record<string, string | number | boolean | undefined>;
    headers?: HeadersInit;
  } = {},
): Promise<TResponse> {
  const { method = "GET", body, searchParams, headers } = options;

  const url = new URL(path, config.baseUrl);
  if (searchParams) {
    Object.entries(searchParams).forEach(([key, value]) => {
      if (value === undefined) return;
      url.searchParams.set(key, String(value));
    });
  }

  const response = await fetch(url.toString(), {
    method,
    headers: {
      "Content-Type": "application/json",
      ...headers,
    },
    body: body ? JSON.stringify(body) : undefined,
    credentials: "include",
  });

  const contentType = response.headers.get("content-type");
  const isJson = contentType?.includes("application/json");
  const payload = isJson ? await response.json() : await response.text();

  if (!response.ok) {
    const errorShape: HttpErrorShape = {
      status: response.status,
      message:
        (isJson && (payload as any)?.message) ||
        response.statusText ||
        "Request failed",
      code: isJson ? (payload as any)?.code : undefined,
      details: isJson ? (payload as any)?.details : payload,
    };

    throw new HttpError(errorShape);
  }

  return payload as TResponse;
}

