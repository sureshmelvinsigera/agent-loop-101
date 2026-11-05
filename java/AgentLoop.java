/*
 * The Python agent loop from main.py, in plain Java 21 with no dependencies.
 *
 * Run (no build tool needed):
 *     export ANTHROPIC_API_KEY=sk-ant-...
 *     java AgentLoop.java
 *     java AgentLoop.java "What is 1234 * 5678, and what's the weather in NYC?"
 *
 * Why no SDK? So you can see exactly what goes over the wire. An "agent" is a loop
 * around one HTTP endpoint (POST /v1/messages):
 *   1. Send messages + tool definitions.
 *   2. If stop_reason == "tool_use", run the tool(s) yourself and send the output back
 *      as a "tool_result" block.
 *   3. Repeat until stop_reason is anything else (usually "end_turn").
 *
 * In real projects use the official Anthropic Java SDK (or Jackson for JSON). The tiny
 * JSON reader/writer at the bottom exists only to keep this file dependency-free.
 */
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;

public class AgentLoop {

    static final String MODEL = "claude-sonnet-5-5";
    static final String BASE_URL =
            System.getenv().getOrDefault("ANTHROPIC_BASE_URL", "https://api.anthropic.com");
    static final HttpClient HTTP = HttpClient.newHttpClient();

    // ---- 1. Tool definitions: a name, a description, and a JSON Schema ----------
    // The description is a prompt: the model decides when to call a tool from it.
    static final List<Object> TOOLS = List.of(
            tool("calculate", "Evaluate a basic arithmetic expression like '12 * (3 + 4)'.", "expression"),
            tool("get_weather", "Get the current weather for a city (fake data for the demo).", "city"));

    static Map<String, Object> tool(String name, String description, String stringParam) {
        return Map.of(
                "name", name,
                "description", description,
                "input_schema", Map.of(
                        "type", "object",
                        "properties", Map.of(stringParam, Map.of("type", "string")),
                        "required", List.of(stringParam)));
    }

    // ---- 2. Tool implementations: plain Java functions --------------------------
    // The model never sees this code. It only sees the definitions above.
    static final Map<String, Function<Map<String, Object>, String>> IMPLEMENTATIONS = Map.of(
            "calculate", input -> calculate((String) input.get("expression")),
            "get_weather", input -> (input.get("city") + ": 58F, light rain"));

    static String calculate(String expression) {
        if (!expression.matches("[0-9+\\-*/(). ]+")) {
            return "Error: only basic arithmetic is allowed.";
        }
        double v = new Calc(expression).parse();
        boolean whole = v == Math.rint(v) && Math.abs(v) < 1e15;
        return whole ? String.valueOf((long) v) : String.valueOf(v);
    }

    // ---- 3. The agent loop ------------------------------------------------------
    @SuppressWarnings("unchecked")
    static String runAgent(String userPrompt, int maxTurns) throws Exception {
        List<Object> messages = new ArrayList<>();
        messages.add(Map.of("role", "user", "content", userPrompt));

        for (int turn = 0; turn < maxTurns; turn++) {
            Map<String, Object> request = Map.of(
                    "model", MODEL,
                    "max_tokens", 1024,
                    "tools", TOOLS,
                    "messages", messages);
            Map<String, Object> response = post(request);
            List<Object> content = (List<Object>) response.get("content");

            // Keep the assistant turn (including its tool_use blocks) in history.
            // The API needs it to match each tool_result to its request.
            List<Object> assistantBlocks = new ArrayList<>();
            for (Object block : content) {
                assistantBlocks.add(toParam((Map<String, Object>) block));
            }
            messages.add(Map.of("role", "assistant", "content", assistantBlocks));

            if (!"tool_use".equals(response.get("stop_reason"))) {
                // Done: return the final text.
                StringBuilder text = new StringBuilder();
                for (Object o : content) {
                    Map<String, Object> block = (Map<String, Object>) o;
                    if ("text".equals(block.get("type"))) {
                        text.append(block.get("text"));
                    }
                }
                return text.toString();
            }

            // Run every tool the model asked for, then reply with the results.
            List<Object> results = new ArrayList<>();
            for (Object o : content) {
                Map<String, Object> block = (Map<String, Object>) o;
                if (!"tool_use".equals(block.get("type"))) {
                    continue;
                }
                String name = (String) block.get("name");
                Map<String, Object> input = (Map<String, Object>) block.get("input");
                System.out.println("[turn " + turn + "] tool call: " + name + "(" + Json.write(input) + ")");

                String output;
                boolean isError = false;
                try {
                    Function<Map<String, Object>, String> impl = IMPLEMENTATIONS.get(name);
                    if (impl == null) {
                        throw new IllegalArgumentException("unknown tool " + name);
                    }
                    output = impl.apply(input);
                } catch (Exception e) {
                    // Return errors to the model so it can recover instead of crashing.
                    output = "Error: " + e.getMessage();
                    isError = true;
                }

                Map<String, Object> result = new LinkedHashMap<>();
                result.put("type", "tool_result");
                result.put("tool_use_id", block.get("id"));
                result.put("content", output);
                if (isError) {
                    result.put("is_error", true); // tells the model the tool FAILED
                }
                results.add(result);
            }
            messages.add(Map.of("role", "user", "content", results));
        }
        return "Stopped: hit max_turns.";
    }

    /** Send back only the fields the API needs from each response block. */
    static Map<String, Object> toParam(Map<String, Object> block) {
        String type = (String) block.get("type");
        if ("text".equals(type)) {
            return Map.of("type", "text", "text", block.get("text"));
        }
        if ("tool_use".equals(type)) {
            return Map.of("type", "tool_use", "id", block.get("id"),
                    "name", block.get("name"), "input", block.get("input"));
        }
        return block;
    }

    /** One HTTP call: POST /v1/messages. This is the entire "API". */
    @SuppressWarnings("unchecked")
    static Map<String, Object> post(Map<String, Object> body) throws IOException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder(URI.create(BASE_URL + "/v1/messages"))
                .header("x-api-key", System.getenv("ANTHROPIC_API_KEY"))
                .header("anthropic-version", "2023-06-01")
                .header("content-type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(Json.write(body)))
                .build();
        HttpResponse<String> response = HTTP.send(request, HttpResponse.BodyHandlers.ofString());
        if (response.statusCode() != 200) {
            throw new IOException("HTTP " + response.statusCode() + ": " + response.body());
        }
        return (Map<String, Object>) Json.parse(response.body());
    }

    public static void main(String[] args) throws Exception {
        if (System.getenv("ANTHROPIC_API_KEY") == null) {
            System.err.println("Set ANTHROPIC_API_KEY first.");
            System.exit(1);
        }
        String prompt = args.length > 0
                ? String.join(" ", args)
                : "What's 1234 * 5678, and should I bring an umbrella in New York?";
        System.out.println(runAgent(prompt, 10));
    }

    // ---- Exercises (great teaching material too) --------------------------------
    // 1. Add a third tool, e.g. search_notes(query), and watch the model pick it.
    // 2. Make a tool throw on purpose and watch how the model recovers (is_error).
    // 3. Add a "system" field to the request body and see how behavior changes.
    // 4. Replace the hand-written JSON with Jackson, or this file with the official SDK.

    // =============================================================================
    // Plumbing below: a calculator and a minimal JSON reader/writer. Not the lesson.
    // =============================================================================

    /** Recursive-descent arithmetic: + - * / parentheses and unary minus. */
    static final class Calc {
        private final String s;
        private int i;

        Calc(String s) {
            this.s = s;
        }

        double parse() {
            double v = expr();
            skip();
            if (i != s.length()) {
                throw new IllegalArgumentException("unexpected '" + s.charAt(i) + "' at position " + i);
            }
            return v;
        }

        private double expr() {
            double v = term();
            while (true) {
                skip();
                if (eat('+')) v += term();
                else if (eat('-')) v -= term();
                else return v;
            }
        }

        private double term() {
            double v = factor();
            while (true) {
                skip();
                if (eat('*')) {
                    v *= factor();
                } else if (eat('/')) {
                    double d = factor();
                    if (d == 0) throw new ArithmeticException("division by zero");
                    v /= d;
                } else {
                    return v;
                }
            }
        }

        private double factor() {
            skip();
            if (eat('-')) return -factor();
            if (eat('(')) {
                double v = expr();
                skip();
                if (!eat(')')) throw new IllegalArgumentException("missing )");
                return v;
            }
            int start = i;
            while (i < s.length() && (Character.isDigit(s.charAt(i)) || s.charAt(i) == '.')) i++;
            if (start == i) throw new IllegalArgumentException("expected a number at position " + i);
            return Double.parseDouble(s.substring(start, i));
        }

        private void skip() {
            while (i < s.length() && s.charAt(i) == ' ') i++;
        }

        private boolean eat(char c) {
            if (i < s.length() && s.charAt(i) == c) {
                i++;
                return true;
            }
            return false;
        }
    }

    /** Minimal JSON: objects -> Map, arrays -> List, plus String, Long/Double, Boolean, null. */
    static final class Json {
        private final String s;
        private int i;

        private Json(String s) {
            this.s = s;
        }

        static Object parse(String text) {
            Json p = new Json(text);
            Object v = p.value();
            p.ws();
            if (p.i != p.s.length()) throw p.error("trailing data");
            return v;
        }

        static String write(Object v) {
            StringBuilder sb = new StringBuilder();
            write(v, sb);
            return sb.toString();
        }

        private static void write(Object v, StringBuilder sb) {
            if (v == null) {
                sb.append("null");
            } else if (v instanceof String str) {
                quote(str, sb);
            } else if (v instanceof Number || v instanceof Boolean) {
                sb.append(v);
            } else if (v instanceof Map<?, ?> map) {
                sb.append('{');
                boolean first = true;
                for (Map.Entry<?, ?> e : map.entrySet()) {
                    if (!first) sb.append(',');
                    first = false;
                    quote((String) e.getKey(), sb);
                    sb.append(':');
                    write(e.getValue(), sb);
                }
                sb.append('}');
            } else if (v instanceof List<?> list) {
                sb.append('[');
                for (int k = 0; k < list.size(); k++) {
                    if (k > 0) sb.append(',');
                    write(list.get(k), sb);
                }
                sb.append(']');
            } else {
                throw new IllegalArgumentException("Cannot serialize " + v.getClass());
            }
        }

        private static void quote(String str, StringBuilder sb) {
            sb.append('"');
            for (char c : str.toCharArray()) {
                switch (c) {
                    case '"' -> sb.append("\\\"");
                    case '\\' -> sb.append("\\\\");
                    case '\n' -> sb.append("\\n");
                    case '\r' -> sb.append("\\r");
                    case '\t' -> sb.append("\\t");
                    default -> {
                        if (c < 0x20) sb.append(String.format("\\u%04x", (int) c));
                        else sb.append(c);
                    }
                }
            }
            sb.append('"');
        }

        private Object value() {
            ws();
            if (i >= s.length()) throw error("unexpected end");
            return switch (s.charAt(i)) {
                case '{' -> object();
                case '[' -> array();
                case '"' -> string();
                case 't' -> literal("true", Boolean.TRUE);
                case 'f' -> literal("false", Boolean.FALSE);
                case 'n' -> literal("null", null);
                default -> number();
            };
        }

        private Map<String, Object> object() {
            Map<String, Object> map = new LinkedHashMap<>();
            i++; // {
            ws();
            if (peek() == '}') {
                i++;
                return map;
            }
            while (true) {
                ws();
                String key = string();
                ws();
                expect(':');
                map.put(key, value());
                ws();
                if (peek() == ',') {
                    i++;
                } else {
                    expect('}');
                    return map;
                }
            }
        }

        private List<Object> array() {
            List<Object> list = new ArrayList<>();
            i++; // [
            ws();
            if (peek() == ']') {
                i++;
                return list;
            }
            while (true) {
                list.add(value());
                ws();
                if (peek() == ',') {
                    i++;
                } else {
                    expect(']');
                    return list;
                }
            }
        }

        private String string() {
            expect('"');
            StringBuilder sb = new StringBuilder();
            while (true) {
                if (i >= s.length()) throw error("unterminated string");
                char c = s.charAt(i++);
                if (c == '"') return sb.toString();
                if (c != '\\') {
                    sb.append(c);
                    continue;
                }
                char e = s.charAt(i++);
                switch (e) {
                    case '"', '\\', '/' -> sb.append(e);
                    case 'n' -> sb.append('\n');
                    case 'r' -> sb.append('\r');
                    case 't' -> sb.append('\t');
                    case 'b' -> sb.append('\b');
                    case 'f' -> sb.append('\f');
                    case 'u' -> {
                        sb.append((char) Integer.parseInt(s.substring(i, i + 4), 16));
                        i += 4;
                    }
                    default -> throw error("bad escape \\" + e);
                }
            }
        }

        private Object number() {
            int start = i;
            while (i < s.length() && "+-0123456789.eE".indexOf(s.charAt(i)) >= 0) i++;
            if (start == i) throw error("unexpected character '" + s.charAt(i) + "'");
            String t = s.substring(start, i);
            return t.matches("-?\\d+") ? (Object) Long.parseLong(t) : (Object) Double.parseDouble(t);
        }

        private Object literal(String word, Object result) {
            if (!s.startsWith(word, i)) throw error("expected " + word);
            i += word.length();
            return result;
        }

        private void ws() {
            while (i < s.length() && Character.isWhitespace(s.charAt(i))) i++;
        }

        private char peek() {
            if (i >= s.length()) throw error("unexpected end");
            return s.charAt(i);
        }

        private void expect(char c) {
            if (peek() != c) throw error("expected '" + c + "'");
            i++;
        }

        private IllegalArgumentException error(String msg) {
            return new IllegalArgumentException("JSON error at " + i + ": " + msg);
        }
    }
}
