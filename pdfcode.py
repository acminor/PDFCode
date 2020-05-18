from dataclasses import dataclass
from typing import Optional, List
from pathlib import Path
import sqlite3 as sq3
import codecs
import click

def src_get_line_link(file_num, line_num):
    return '{}x{}'.format(file_num, line_num)

@dataclass
class GtagData:
    file_num: int
    file_name: str
    tagname: str
    line_num: int
    code: str

    def get_link(self):
        return src_get_line_link(self.file_num, self.line_num)

@dataclass
class GRtagData:
    file_num: int
    file_name: str
    tagname: str
    line_nums: List[int]

    def get_link(self, line_num=None):
        if line_num is None:
            return src_get_line_link(self.file_num, self.line_nums[0])
        else:
            return src_get_line_link(self.file_num, line_num)

@dataclass
class RevPage:
    revs: List[GRtagData]

    def get_link(self):
        return 'revpage{}'.format(self.revs[0].tagname)
    def get_page(self):
        def sort_files_key(a):
            c_a = a.count('/')

            # closest to root then alphabetical order
            return '{}_{}'.format(c_a, a)

        sorted_revs = sorted(self.revs,
                             key=lambda x:
                             sort_files_key(x.file_name))

        page = []
        for rev in sorted_revs:
            links = [rev.get_link(ln) for ln in rev.line_nums]
            locations = []

            current_len = len(rev.file_name)
            num_multiline = 0
            current_locations = ''
            for line_num, link in zip(rev.line_nums, links):
                current_locations += ":{}\\hyperlink{{{}}}{{$^R$}}".format(line_num, link)
                current_len += len(str(line_num))+1
                if current_len > 60:
                    current_len = 0
                    num_multiline += 1
                    locations.append(current_locations)
                    current_locations = ''

            if current_locations != '':
                locations.append(current_locations)

            for i, locations in enumerate(locations):
                if i == 0:
                    line = (
                        '\\verb|{}|'.format(rev.tagname),
                        '\\verb|{}|{}'.format(
                            rev.file_name, locations)
                    )
                else:
                    line = (
                        '',
                        '{}'.format(locations)
                    )
                page.append(line)

        table = [' & '.join(l) + '\\\\' for l in page]
        page = '''\\begin{{xtabular}}{{cl}}
        {}
        \\end{{xtabular}}'''.format('\n'.join(table))

        wrapper = '''{{\Huge \\verb|{}|}} \\hypertarget{{{}}}{{}}
        \\newline
        \\vskip 1em
{}
        \\vskip 1em
        '''.format(self.revs[0].tagname,
                   self.get_link(),
                   page)

        return wrapper

@dataclass
class DefPage:
    defs: List[GtagData]

    def get_link(self):
        return 'defpage{}'.format(self.defs[0].tagname)
    def get_page(self):
        def sort_files_key(a):
            c_a = a.count('/')

            # closest to root then alphabetical order
            return '{}_{}'.format(c_a, a)

        sorted_defs = sorted(self.defs,
                             key=lambda x:
                             sort_files_key(x.file_name))

        page = []
        for definition in sorted_defs:
            link = definition.get_link()
            location = "{}:{}".format(definition.file_name,
                                      definition.line_num)
            code = inline_pygmentize(
                definition.file_name,
                code_snippet_fix_brackets(
                    definition.code,
                    (('{', '@$\\lbrace$@'),
                     ('}', '@$\\rbrace$@'))
                )
            )
            line = (
                '\\verb|{}|\\hyperlink{{{}}}{{$^D$}}'.format(
                    definition.tagname, link),
                '\\verb|{}|'.format(location),
                '{{\\footnotesize {}}}'.format(code)
            )

            page.append(line)

        table = [' & '.join(l) + '\\\\' for l in page]
        page = '''\\begin{{tabular}}{{ccc}}
        {}
        \\end{{tabular}}'''.format('\n'.join(table))

        wrapper = '''{{\Huge \\verb|{}|}} \\hypertarget{{{}}}{{}}
        \\newline
        \\vskip 1em
{}
        \\vskip 1em
        '''.format(self.defs[0].tagname,
                   self.get_link(),
                   page)

        return wrapper

class Gtags:
    def __init__(self):
        self.gpath_db: sq3.Connection = sq3.connect('GPATH')
        self.gtags_db: sq3.Connection = sq3.connect('GTAGS')
        self.grtags_db: sq3.Connection = sq3.connect('GRTAGS')

        self.gpath_db.row_factory = sq3.Row
        self.gtags_db.row_factory = sq3.Row
        self.grtags_db.row_factory = sq3.Row

        self.gpath_db.text_factory = \
            lambda x: codecs.decode(x, errors='backslashreplace')
        self.gtags_db.text_factory = \
            lambda x: codecs.decode(x, errors='backslashreplace')
        self.grtags_db.text_factory = \
            lambda x: codecs.decode(x, errors='backslashreplace')

    def get_files(self):
        c = self.gpath_db.cursor()
        c.execute('select * from db')
        files = c.fetchall()

        files = [(f['key'], int(f['dat']))
                    for f in files if f['dat'].isnumeric()]

        return files

# TODO type out pages - dict of key: tag_name, val: link page
def process_file(gtags: Gtags, file, def_pages, rev_pages, full_lines, use_rev=False):
    code = pygmentize(file[0])

    # unrecognized extension
    if code is None:
        return None, None

    code = \
        process_reverse_links(gtags, file, code, def_pages)

    if use_rev:
        code = \
            process_definitions(gtags, file, code, rev_pages)

    file_num = file[1]
    # NOTE -1 to avoid including \end{minted} line
    for i in range(1, len(code) - 1):
        # NOTE fix to pygments issue with latex in comments
        if full_lines.get(file_num) and i not in full_lines[file_num]:
            # NOTE fix to pygments issue with comments and underscores
            # hack as not guaranteed to be a comment
            code[i] = code[i].replace('\\', '\\\\')
            # hack as not guaranteed to be a comment
            code[i] = code[i].replace('_', '@\\_@')
            # hack as not guaranteed to be a comment
            code[i] = code[i].replace('$', '\$')
            continue
        elif full_lines.get(file_num) is None:
            # hack as not guaranteed to be a comment
            code[i] = code[i].replace('\\', '\\\\')
            # hack as not guaranteed to be a comment
            code[i] = code[i].replace('_', '@\\_@')
            # hack as not guaranteed to be a comment
            code[i] = code[i].replace('$', '\$')
            continue

        # NOTE not from 0 to avoid including \begin{minted} line
        code[i] = '@\\hypertarget{{{}}}{{}}@'.format(
            src_get_line_link(file_num, i)) + code[i]

    # name and code
    return file[0], code

KNOWN_EXTS = {
    '.c': 'c',
    '.h': 'c',
    '.hpp': 'c++',
    '.cpp': 'c++',
    '.py': 'python',
}

def sort_files_by_depth_and_order_key(a):
            c_a = a.count('/')

            # closest to root then alphabetical order
            return '{}_{}'.format(c_a, a)

def inline_pygmentize(file_name, code):
    wrapper = '\\mintinline[escapeinside=@@]{{{}}}{{{}}}'

    ext = Path(file_name).suffix
    if KNOWN_EXTS.get(ext):
        return wrapper.format(KNOWN_EXTS[ext], code)
    else:
        return None

def pygmentize(file):
    try:
        with open(file, 'r') as code:
            # NOTE XXX happens to workout that GnuGlobal references lines
            # from 1 and Python from 0 so that we never search inside of the
            # beginning tags and everything is indexed properly
            # with implicit +1
            wrapper = """\\begin{{minted}}[escapeinside=@@, linenos]{{{}}}
    {}
    \\end{{minted}}
            """

            #print(file)
            ext = Path(file).suffix
            if KNOWN_EXTS.get(ext):
                return wrapper.format(
                    KNOWN_EXTS[ext], code.read()).split('\n')
            else:
                #print('NONE {}'.format(file))
                return None
    except: # some file read error
        return None

# computes at barriers with assumption they are not nested from the start
# - this should keep them un-nested
def at_barriers(text):
    at_barriers = []

    left_at = -1
    for i, char in enumerate(text):
        if char == '@' and left_at != -1:
            at_barriers.append(set(range(left_at, i)))
            left_at = -1
        elif char == '@' and left_at == -1:
            left_at = i
        else:
            pass

    return at_barriers

def uncompress(text, tagname):
    u_text = ''
    prev_char = text[0]
    i = 0
    while i < len(text):
        char = text[i]
        if prev_char == '@':
            if char == 'n':
                u_text += tagname
            elif char == 'd':
                u_text += 'define'
            elif char == 't':
                u_text += 'typedef'
            elif char == '{':
                digit = ''
                while char != '}':
                    i += 1
                    char = text[i]
                    digit += char
                digit = digit[:len(digit) - 2]
                digit = int(digit)
                u_text += digit*' '
            elif char.isnumeric():
                digit = int(char)
                u_text += digit*' '
            else:
                u_text += '@'
        elif char == '@':
            pass
        else:
            u_text += char

        prev_char = char
        i += 1

    return u_text

def get_def_pages(gtags):
    g_c = gtags.gtags_db.cursor()
    pages = dict()

    g_c.execute('select * from db')
    tag = g_c.fetchone()

    # file number to name
    file_transformer = dict([reversed(f)
                             for f in gtags.get_files()])

    while tag != None:
        # TODO fix for rev and fix issue with @{} in source code
        try:
            u_data = uncompress(tag['dat'], tag['key']) \
                .split(' ', maxsplit=3)
        except:
            tag = g_c.fetchone()
            continue
        #print(u_data)

        if len(u_data) != 4 or not u_data[0].isnumeric():
            tag = g_c.fetchone()
            continue

        file_num = int(u_data[0])
        tagname = u_data[1].strip()
        assert(tagname == tag['key'].strip())
        line_num = int(u_data[2])
        definition = u_data[3]

        file_name = file_transformer[file_num]
        tagdata = GtagData(file_num, file_name, tagname,
                            line_num, definition)

        if pages.get(tag['key']):
            pages[tag['key']].append(tagdata)
        else:
            pages[tag['key']] = [tagdata]

        tag = g_c.fetchone()

    processed_pages = dict()
    for tag, tagdata in pages.items():
        if len(tagdata) > 1:
            processed_pages[tag] = DefPage(tagdata)
        else:
            processed_pages[tag] = tagdata[0]

    return processed_pages

def get_rev_pages(gtags):
    gr_c = gtags.grtags_db.cursor()
    pages = dict()

    gr_c.execute('select * from db')
    tag = gr_c.fetchone()

    file_transformer = dict([reversed(f)
                             for f in gtags.get_files()])

    while tag != None:
        u_data = uncompress(tag['dat'], tag['key']) \
            .split(' ', maxsplit=2)
        #print(u_data)

        if len(u_data) != 3 or not u_data[0].isnumeric():
            tag = gr_c.fetchone()
            continue

        file_num = int(u_data[0])
        tagname = u_data[1].strip()
        assert(tagname == tag['key'].strip())
        line_nums = parse_grtags_lines_list(u_data[2])

        file_name = file_transformer[file_num]
        tagdata = GRtagData(file_num, file_name, tagname,
                            line_nums)

        if pages.get(tag['key']):
            pages[tag['key']].append(tagdata)
        else:
            pages[tag['key']] = [tagdata]

        tag = gr_c.fetchone()

    processed_pages = dict()
    for tag, tagdata in pages.items():
        if len(tagdata) > 1:
            processed_pages[tag] = RevPage(tagdata)
        elif len(tagdata[0].line_nums) > 1:
            processed_pages[tag] = RevPage(tagdata)
        else:
            processed_pages[tag] = tagdata[0]

    return processed_pages

def parse_grtags_lines_list(text):
    current_num = 0
    line_nums = []
    for num in text.split(','):
        # Assumes that 10,11-3 -> 10, 21, 22, 23, 24
        if '-' in num:
            num, range_num = num.split('-')

            range_num = int(range_num)
            num = int(num) + current_num

            for i in range(0, range_num + 1):
                line_nums.append(num+i)

            current_num = num + range_num
        else:
            line_nums.append(current_num + int(num))
            current_num = current_num + int(num)

    return line_nums

def process_reverse_links(gtags, file, code, def_pages):
    file_num = file[1]

    #print(('fn', file_num))
    gr_c = gtags.grtags_db.cursor()
    gr_c.execute('select * from db where extra=?',
                 [str(file_num)])
    rev_tags = gr_c.fetchall()

    #print(rev_tags)
    for tag in rev_tags:
        tagname = tag['key']

        if not def_pages.get(tagname):
            #print('no def page: {}'.format(tagname))
            continue
        else:
            pass
            #print('def page: {}'.format(tagname))

        link = def_pages[tagname].get_link()

        u_data = uncompress(tag['dat'], tagname).split(' ')
        assert(file_num == int(u_data[0]))
        assert(tagname == u_data[1])

        line_nums = parse_grtags_lines_list(u_data[2])

        #print(u_data[2])
        #print(line_nums)
        for num in line_nums:
            num_occurances = code[num].count(tagname)
            assert(num_occurances > 0)

            prev_index = 0
            for _ in range(0, num_occurances):
                # do not next @@ declarations
                at_bars = at_barriers(code[num])

                start_index = code[num] \
                    .find(tagname, prev_index)
                assert(start_index != -1)

                # NOTE heuristic to play it safe and
                # ignore potential partial matches (c-centric)

                if start_index + len(tagname) < len(code[num]):
                    test_char = code[num][start_index + len(tagname)]
                    if test_char.isalnum() or test_char == '_':
                        continue
                elif start_index - 1 > 0:
                    test_char = code[num][start_index - 1]
                    if test_char.isalnum() or test_char == '_':
                        continue
                elif start_index + len(tagname) == len(code[num]):
                    pass # safe b/c last
                else: # be safe and continue (shouldn't happen)
                    continue

                #print(("At Bars", at_bars))
                if any([(start_index in at_bar) for at_bar in at_bars]):
                    continue

                # XXX potential corruptions if code uses latex names for things
                # - at some point should fix by aliasing used functions to
                #   invalid names in most programming languages (if possible)

                prev_index = start_index + len(tagname)

                #print(code[num])
                #print(code[num][:start_index + len(tagname)])
                #print(code[num][start_index+len(tagname):])

                code[num] = code[num][:start_index + len(tagname)] \
                    + '@\\hyperlink{{{}}}{{$^D$}}@' \
                         .format(link) \
                    + code[num][start_index+len(tagname):]
                #print(code[num])
    return code

def process_definitions(gtags, file, code, rev_pages, full_lines):
    file_num = file[1]

    #print(('fn', file_num))
    g_c = gtags.gtags_db.cursor()
    g_c.execute('select * from db where extra=?',
                 [str(file_num)])
    def_tags = g_c.fetchall()

    #print(def_tags)
    for tag in def_tags:
        tagname = tag['key']

        if not rev_pages.get(tagname):
            #print('no rev page: {}'.format(tagname))
            continue
        else:
            pass
            #print('rev page: {}'.format(tagname))

        link = rev_pages[tagname].get_link()

        u_data = uncompress(tag['dat'], tag['key']) \
            .split(' ', maxsplit=3)
        #print(u_data)

        if len(u_data) != 4 or not u_data[0].isnumeric():
            continue

        file_num = int(u_data[0])
        tagname = u_data[1].strip()
        assert(tagname == tag['key'].strip())
        line_num = int(u_data[2])
        definition = u_data[3]

        # NOTE heuristic to go with leftmost match and veto others
        count = code[line_num].count(tagname)
        valid_index = -1
        if count > 1:
            prev_index = 0
            for i in range(0, count):
                current_index = code[line_num].find(tagname, prev_index)
                # would be better to make this a per
                # language thing (specifically for languages
                # which use hyphens in variables names)
                if current_index + len(tagname) < len(code[line_num]):
                    #print('test after')
                    test_char = code[line_num][current_index + len(tagname)]
                    # this is c-centric for now
                    # - not lisp centric
                    if test_char.isalnum() or test_char == '_':
                        pass
                    elif current_index - 1 > 0:
                        #print('test before')
                        test_char = code[line_num][current_index - 1]
                        if test_char.isalnum() or test_char == '_':
                            pass
                        else:
                            valid_index = current_index
                            break
                    else: # no characters before
                        valid_index = current_index
                        break
                # end of line name is valid
                elif current_index + len(tagname) == len(code[line_num]):
                    valid_index = current_index

                prev_index = current_index + len(tagname)
        else:
            valid_index = code[line_num].find(tagname)

        if valid_index == -1:
            #print(code[line_num])
            raise Exception('Heuristic failure: check language details')

        start_index = code[line_num] \
            .find(tagname, valid_index)

        # do not next @@ declarations
        at_bars = at_barriers(code[line_num])
        if any([(start_index in at_bar) for at_bar in at_bars]):
            continue

        #print(code[line_num])
        assert(start_index != -1)

        prev_index = start_index + 1

        code[line_num] = code[line_num][:start_index + len(tagname)] \
            + '@\\hyperlink{{{}}}{{$^R$}}@' \
                    .format(link) \
            + code[line_num][start_index+len(tagname):]
        #print(code[line_num])

    return code

def get_full_lines(gtags):
    gr_c = gtags.grtags_db.cursor()
    g_c = gtags.gtags_db.cursor()

    per_file_full_lines = dict()

    gr_c.execute('select * from db')
    rev_tags = gr_c.fetchall()
    g_c.execute('select * from db')
    def_tags = g_c.fetchall()

    for tag in rev_tags:
        tag = tag['dat']
        file_num = tag.split(' ')[0]
        if not file_num.isnumeric():
            continue

        file_num = int(file_num)
        line_nums = parse_grtags_lines_list(tag.split(' ')[2])

        if per_file_full_lines.get(file_num):
            per_file_full_lines[file_num] += line_nums
        else:
            per_file_full_lines[file_num] = line_nums

    for tag in def_tags:
        tag = tag['dat']
        file_num = tag.split(' ')[0]
        if not file_num.isnumeric():
            continue

        file_num = int(file_num)
        line_num = int(tag.split(' ')[2])

        if per_file_full_lines.get(file_num):
            per_file_full_lines[file_num] += [line_num]
        else:
            per_file_full_lines[file_num] = [line_num]

    return per_file_full_lines

def latex_escape(text):
    text = text.replace('_', '\\_')
    return text

def code_snippet_fix_brackets(code, brackets):
    # TODO come up with better scheme
    left_b_original = brackets[0][0]
    left_b_replacement = brackets[0][1]
    right_b_original = brackets[1][0]
    right_b_replacement = brackets[1][1]

    code = code.replace(left_b_original, left_b_replacement)
    code = code.replace(right_b_original, right_b_replacement)

    return code

@click.command()
@click.option('--use-rev', default=False)
def main(use_rev):
    gtags = Gtags()

    files = gtags.get_files()
    def_pages = get_def_pages(gtags)
    rev_pages = get_rev_pages(gtags)

    full_lines = get_full_lines(gtags)

    all_codes = []
    for file in files:
        file_name, code = process_file(gtags, file, def_pages, rev_pages, full_lines, use_rev)

        if file_name is None or code is None:
            pass
        else:
            all_codes.append((file_name, code))

    all_codes = sorted(all_codes, key=lambda x: x[0])
    all_codes = ['\\subsection{{\\texttt{{{}}}}}\n{}'
                 .format(
                     latex_escape(x[0]),
                     '\n'.join(x[1])
                 ) for x in all_codes]
    all_codes = ['\section{Source Files}'] + all_codes

    all_codes.append(
        '\\section{{Section Definition References}}')
    for page in def_pages.values():
        if isinstance(page, DefPage):
            all_codes.append(page.get_page())

    if use_rev:
        all_codes.append(
            '\\section{{Section Reverse References}}')
        for page in rev_pages.values():
            if isinstance(page, RevPage):
                all_codes.append(page.get_page())

    with open('test.tex', 'w+') as test_out:
        output = '''\\documentclass{{article}}
        \\usepackage{{fontawesome}}
        \\usepackage{{minted}}
        \\usepackage{{hyperref}}
        \\usepackage{{xtab}}
        \\usepackage[margin=0.5in]{{geometry}}

        \\hypersetup {{
          colorlinks=true,
          urlcolor=cyan,
        }}

        \\title{{\\texttt{{{}}}}}
        \\author{{Generated by PDFCode}}
        \\date{{\\today}}

        \\begin{{document}}
        \\maketitle
        \\tableofcontents
        {}
        \\end{{document}}
        '''.format(
            latex_escape(Path.cwd().stem),
            '\n'.join(all_codes)
        )
        test_out.write(output)

    gtags.gpath_db.close()
    gtags.gtags_db.close()
    gtags.grtags_db.close()

if __name__ == '__main__':
    main()
