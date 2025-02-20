class BenchmarkRegistry:
    _classes = {}

    @classmethod
    def register(cls, name, inp_type):
        def decorator(registered_class):
            cls._classes[name] = (inp_type, registered_class)
            return registered_class

        return decorator

    @classmethod
    def get_all_classes(cls):
        return cls._classes


class EvaluatorRegistry:
    _classes = {}

    @classmethod
    def register(cls, name):
        def decorator(registered_class):
            cls._classes[name] = registered_class
            return registered_class

        return decorator

    @classmethod
    def get_all_classes(cls):
        return cls._classes
