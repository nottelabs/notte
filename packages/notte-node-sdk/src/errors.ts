export class NotteAPIError extends Error {
  readonly statusCode: number;
  readonly errorBody: unknown;
  readonly path: string;

  constructor(statusCode: number, errorBody: unknown, path: string) {
    const message =
      typeof errorBody === "object" && errorBody !== null && "detail" in errorBody
        ? String((errorBody as Record<string, unknown>).detail)
        : typeof errorBody === "object" && errorBody !== null && "message" in errorBody
          ? String((errorBody as Record<string, unknown>).message)
          : typeof errorBody === "string" && errorBody.length > 0
            ? errorBody
            : `API request failed with status ${statusCode}`;
    super(`${message} (${path})`);
    this.name = "NotteAPIError";
    this.statusCode = statusCode;
    this.errorBody = errorBody;
    this.path = path;
  }
}

export class AuthenticationError extends Error {
  constructor(message = "NOTTE_API_KEY needs to be provided") {
    super(message);
    this.name = "AuthenticationError";
  }
}

export class InvalidRequestError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "InvalidRequestError";
  }
}
