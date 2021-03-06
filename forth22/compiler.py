INDENT = "    "
def indented(lst):
    return ["%s%s" % (INDENT, s) for s in lst]

def stack_swap(indices):
    max_index = int(max(indices))
    return ["s%s:" % indices] +\
           indented("popdata r%s" % (i+1) for i in range(max_index)) +\
           indented("pushdata r%s" % i for i in reversed(indices)) +\
           indented(["ret"])

array_template = """
%(array)s.len:
    pushdata [%(array)s_length]
    ret
%(array)s.push:
%(array)s.append:
    popdata r1
    mov r2, [%(array)s_length]
    mov %(width_word)s[%(array)s + %(width)s*r2], r1%(width_word)s
    inc qword [%(array)s_length]
    ret
%(array)s.pop:
    dec qword [%(array)s_length]
    mov r1, [%(array)s_length]
    mov%(width_trunc)s r1, %(width_word)s[%(array)s + %(width)s*r1]
    pushdata r1
    ret
%(array)s.get:
    popdata r1
    mov%(width_trunc)s r1, %(width_word)s[%(array)s + %(width)s*r1]
    pushdata r1
    ret
%(array)s.set_at:
    popdata r1
    popdata r2
    mov [%(array)s + %(width)s*r1], r2%(width_word)s
    ret
%(array)s.address:
    popdata r1
    lea r1, [%(array)s + %(width)s*r1]
    pushdata r1
    ret
"""
array_template = array_template.strip()
# print(array_template % {"array": "array", "width": 8, "width_word": "", "width_char": ""})
def array(name, width=8):
    width_word = {8: ("", ""), 1: ("byte ", "zx")}
    return (array_template % {"array": name, "width": width,
                             "width_word": width_word[width][0],
                             "width_trunc": width_word[width][1]}).split("\n")

def array_footer(name, width=8, size=10000):
    width_char = {8: "q", 1: "b"}
    return ["%s_length: resq 1" % name,
            "%s: res%s %s" % (name, width_char[width], size)]

new_names = {"+": "add", "-": "sub", "*": "mul", "==": "equal",
             "[": "write-loop", "(": "comment", ">": "greater",
             "push:": "push", "pushi:": "pushi", "call": "call-function"}
old_names = {v: k for k, v in new_names.items()}
def rename(s):
    return new_names.get(s, s).replace("-", "_")

def rev_rename(s):
    s = s.replace("_", "-")
    return old_names.get(s, s)

def compile_(commands, stop=None):
    output = []
    while True:
        try:
            command = rename(next(commands))
        except StopIteration:
            return output
        if command == stop:
            return output
        elif command == "write_loop":
            body = compile_(commands, "]")
            assert(next(commands) == "bind:")
            output.append("%s:" % rename(next(commands)))
            output.extend(indented(body + ["ret"]))
        elif command == "comment":
            _ = compile_(commands, ")")
        elif command == "prints(":
            next_command = next(commands)
            inner = []
            while next_command != ")":
                inner.append(next_command)
                next_command = next(commands)
            output.append('prints %s' % " ".join(inner))
        elif command == "pushe:":
            output.append("pushdata %s" % rename(next(commands)))
        elif command == "push":
            next_command = next(commands)
            output.append("pushdata %s" % rename(next_command))
        elif command == "label:":
            output.append("%s:" % rename(next(commands)))
        elif command == "goto:":
            output.append("jmp %s" % rename(next(commands)))
        elif command == "goto_if:":
            output.extend(["popdata r1", "test r1, r1",
                           "jnz %s" % rename(next(commands))])
        elif command == "copyinit:":
            output.append("copyinit %s" % rename(next(commands)))
        elif command == "ret":
            output.append("ret")
        else:
            output.append("call %s" % command)

definitions = {"True": 1, "False": 0, "r1": "rax", "r1byte": "al", "r2": "rcx",
               "r2byte": "cl", "r3": "rdx", "stdin": 0, "stdout": 1,
               "r5": "rbp", "BUFFER_SIZE": 4096}

if __name__ == "__main__":
    import sys
    commands = open("forth.f" if len(sys.argv) < 2 else sys.argv[1]).read()
    commands = iter(commands.split())

    writable = []
    output = open("header.asm").read().split("\n")
    output += compile_(commands)
    output += [line for indices in ["11", "21", "1212", "1312", "231"]
               for line in stack_swap(indices)]

    def add_array(name, width=8, size=10000):
        output.extend(array(name, width))
        writable.extend(array_footer(name, width, size))

    for name in ["call_stack", "memory", "names.keys", "names.values"]:
        add_array(name)
    add_array("strings", 1)
    add_array("input_buffer", 1)
    writable.append("input_buffer_counter: resq 1")
    writable.extend(array_footer("data_stack"))

    names = [rev_rename(line[:-1]) for line in output
             if line.endswith(":") and not line.strip().startswith(".")
             and line.strip()[0] not in "_%"]
    lengths = [len(name)+1 for name in names]
    partial_sum = [sum(lengths[:i]) for i in range(len(lengths))]
    init_data = [
        "init_strings: db " + ", ".join('%s, "%s"' % (len(name), name)
                                       for name in names),
        "init_names.keys: dq " + ", ".join(str(s) for s in partial_sum),
        "init_names.values: dq " + ", ".join(str(i) for i in range(len(names))),
        "primitive_function: dq " + ", ".join([rename(name) for name in names]),
        "None: dq 0",
        "eol: db 10",
        "space: db 32",
        'print_chars: db "0123456789abcdef"']
    definitions["primitive_length"] = len(names)
    definitions["return_index"] = names.index("return")
    definitions["push_index"] = names.index("push:")
    definitions["pushi_index"] = names.index("pushi:")
    definitions["strings_init_length"] = sum(lengths)
    constants = ["%%define %s %s" % kv for kv in sorted(definitions.items())]

    output = ["global _start"] + constants +\
             [""] + output +\
             ["", "section .data"] + init_data +\
             ["", "section .bss"] + writable
    print("\n".join(output))
