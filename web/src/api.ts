export interface ApiErrorBody {
  code: string;
  message: string;
  field?: string;
}

interface Envelope<T> {
  data?: T;
  error?: ApiErrorBody;
}

export class ApiError extends Error {
  readonly code: string;
  readonly field: string | undefined;

  constructor(body: ApiErrorBody) {
    super(body.message);
    this.name = "ApiError";
    this.code = body.code;
    this.field = body.field;
  }
}

const token =
  document
    .querySelector<HTMLMetaElement>('meta[name="time-tracker-token"]')
    ?.getAttribute("content") ?? "";

async function decode<T>(response: Response): Promise<T> {
  const envelope = (await response.json()) as Envelope<T>;
  if (!response.ok || envelope.error) {
    throw new ApiError(
      envelope.error ?? {
        code: "request_failed",
        message: `Request failed (${response.status})`,
      },
    );
  }
  if (envelope.data === undefined) {
    throw new ApiError({
      code: "invalid_response",
      message: "Invalid server response",
    });
  }
  return envelope.data;
}

export async function get<T>(path: string): Promise<T> {
  return decode<T>(
    await fetch(path, { headers: { Accept: "application/json" } }),
  );
}

export async function post<T>(path: string, body: object = {}): Promise<T> {
  return decode<T>(
    await fetch(path, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-Time-Tracker-Token": token,
      },
      body: JSON.stringify(body),
    }),
  );
}
