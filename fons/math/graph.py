def find_path(graph, start, end, path=[]):
        path = path + [start]
        if start == end:
            return path
        if start not in graph.keys():
            return None
        for node in graph[start]:
            if node not in path:
                newpath = find_path(graph, node, end, path)
                if newpath: return newpath
        return None
    

def find_all_paths(graph, start, end, path=[], max_len=None, *, _l=None):
    if _l is None: _l = len(path)
    path = path + [start]
    _l += 1
    if max_len is not None and _l >= max_len:
        return []
    if start == end:
        return [path]
    
    next_l = _l+1
    if (max_len is not None and next_l > max_len) or start not in graph.keys():
        return []
    
    paths = []
    for node in graph[start]:
        if node not in path:
            newpaths = find_all_paths(graph, node, end, path, max_len, _l=_l)
            for newpath in newpaths:
                paths.append(newpath)
    return paths


def find_shortest_path(graph, start, end, path=[]):
        path = path + [start]
        if start == end:
            return path
        if start not in graph.keys():
            return None
        shortest = None
        for node in graph[start]:
            if node not in path:
                newpath = find_shortest_path(graph, node, end, path)
                if newpath:
                    if not shortest or len(newpath) < len(shortest):
                        shortest = newpath
        return shortest


def create_graph(pairs):
    graph = {}
    for pair in pairs:
        p,q = pair
        try: branch = graph[p]
        except KeyError:
            branch = graph[p] = []
        branch.append(q)
    return graph        
    

if __name__ == '__main__':
        graph = {'A': ['B', 'C'],
             'B': ['C', 'D'],
             'C': ['D'],
             'D': ['C'],
             'E': ['F'],
             'F': ['C']}

        print(find_all_paths(graph, 'A', 'D'))

        
